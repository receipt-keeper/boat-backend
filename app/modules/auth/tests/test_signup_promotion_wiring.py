from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TypedDict

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config.settings import Settings
from app.core.db.outbox.orm import OutboxEvent
from app.main import create_app
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.dependencies import get_external_identity_verifier
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.credits.infrastructure.persistence import orm as credits_orm
from app.modules.promotions.infrastructure.persistence import orm as promotions_orm
from app.modules.promotions.tests.signup_promotion_test_support import (
    count_rows,
    seed_active_signup_campaign,
    seed_signup_campaign,
)

_TEST_SETTINGS = Settings(
    jwt_secret_key="x" * 48,
    refresh_token_pepper="p" * 48,
    promotion_beneficiary_hmac_secret="b" * 48,
)


class _FixedExternalIdentityVerifier(ExternalIdentityVerifier):
    def __init__(self, identity: ExternalIdentity) -> None:
        self._identity = identity

    async def verify(self, provider_token: str) -> ExternalIdentity:
        assert provider_token
        return self._identity


def _identity(subject: str) -> ExternalIdentity:
    return ExternalIdentity.create(
        issuer="google",
        subject=subject,
        provider="google",
        email=f"{subject}@example.com",
        name="프로모션 가입 테스트 사용자",
        email_verified=True,
    )


class _SignupPayload(TypedDict):
    idToken: str
    termsAccepted: bool
    privacyAccepted: bool
    termsVersion: str
    privacyVersion: str
    marketingConsent: bool


def _signup_payload() -> _SignupPayload:
    return {
        "idToken": "redacted-provider-token",
        "termsAccepted": True,
        "privacyAccepted": True,
        "termsVersion": "2026-07-12",
        "privacyVersion": "2026-07-12",
        "marketingConsent": False,
    }


@asynccontextmanager
async def _client(
    session_factory: async_sessionmaker[AsyncSession],
    identity: ExternalIdentity,
) -> AsyncIterator[AsyncClient]:
    app = create_app(_TEST_SETTINGS)
    app.state.session_factory = session_factory
    app.dependency_overrides[get_external_identity_verifier] = lambda: (
        _FixedExternalIdentityVerifier(identity)
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_signup_api_redeems_active_campaign_and_exposes_five_credits(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = _identity("active-signup")
    async with postgres_session_factory() as session:
        await seed_active_signup_campaign(session, benefit_amount=5)

    async with _client(postgres_session_factory, identity) as client:
        signup_response = await client.post("/api/v1/auth/signup", json=_signup_payload())
        access_token = signup_response.json()["data"]["accessToken"]
        credits_response = await client.get(
            "/api/v1/credits",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert signup_response.status_code == 201
    assert credits_response.status_code == 200
    assert credits_response.json()["data"] == {
        "totalGrantedCount": 5,
        "usedCount": 0,
        "remainingCount": 5,
    }
    async with postgres_session_factory() as session:
        event_types = tuple(await session.scalars(select(OutboxEvent.event_type)))
        assert await count_rows(session, promotions_orm.PromotionRedemption) == 1
        assert await count_rows(session, credits_orm.CreditTransaction) == 1
    assert Counter(event_types) == Counter(
        {
            "UserRegistered": 1,
            "UserCredentialCreated": 1,
            "PromotionRedemptionGranted": 1,
            "CreditGranted": 1,
        }
    )


async def test_signup_api_succeeds_without_credits_for_inactive_campaign(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = _identity("inactive-signup")
    async with postgres_session_factory() as session:
        now = datetime.now(UTC)
        await seed_signup_campaign(
            session,
            active=False,
            starts_at=now,
            expires_at=now.replace(year=now.year + 1),
            max_redemptions=None,
            times_redeemed=0,
        )

    async with _client(postgres_session_factory, identity) as client:
        signup_response = await client.post("/api/v1/auth/signup", json=_signup_payload())
        access_token = signup_response.json()["data"]["accessToken"]
        credits_response = await client.get(
            "/api/v1/credits",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert signup_response.status_code == 201
    assert credits_response.json()["data"] == {
        "totalGrantedCount": 0,
        "usedCount": 0,
        "remainingCount": 0,
    }


async def test_withdrawal_then_rejoin_keeps_same_issuer_subject_from_second_grant(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = _identity("withdraw-rejoin")
    async with postgres_session_factory() as session:
        await seed_active_signup_campaign(session, benefit_amount=5)

    async with _client(postgres_session_factory, identity) as client:
        first_signup = await client.post("/api/v1/auth/signup", json=_signup_payload())
        first_access_token = first_signup.json()["data"]["accessToken"]
        first_credits = await client.get(
            "/api/v1/credits",
            headers={"Authorization": f"Bearer {first_access_token}"},
        )
        withdrawal = await client.delete(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {first_access_token}"},
        )
        rejoined_signup = await client.post("/api/v1/auth/signup", json=_signup_payload())
        rejoined_access_token = rejoined_signup.json()["data"]["accessToken"]
        rejoined_credits = await client.get(
            "/api/v1/credits",
            headers={"Authorization": f"Bearer {rejoined_access_token}"},
        )

    assert first_signup.status_code == 201
    assert first_credits.json()["data"]["remainingCount"] == 5
    assert withdrawal.status_code == 204
    assert rejoined_signup.status_code == 201
    assert rejoined_credits.json()["data"]["remainingCount"] == 0
    async with postgres_session_factory() as session:
        assert await count_rows(session, promotions_orm.PromotionRedemption) == 1
        assert await count_rows(session, credits_orm.CreditTransaction) == 0
