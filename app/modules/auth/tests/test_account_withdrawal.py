from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config.settings import Settings
from app.main import create_app
from app.modules.auth.dependencies import (
    get_withdrawal_cleanup_command_use_case,
)
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.tokens.jwt import JwtAccessTokenService
from app.modules.credits.infrastructure.persistence import orm as credit_orm
from app.modules.users.application.commands.withdrawal_cleanup.command import (
    WithdrawalCleanupCommand,
)
from app.modules.users.application.commands.withdrawal_cleanup.use_case import (
    WithdrawalCleanupCommandUseCase,
)
from app.modules.users.infrastructure.persistence import orm as users_orm
from tests.support.users_persistence import (
    count_persisted_users,
    create_persisted_user,
    persisted_user_exists,
)

TEST_SETTINGS = Settings(
    jwt_secret_key="x" * 48,
    jwt_issuer="boat-backend-test",
    jwt_audience="boat-api-test",
)


@dataclass(frozen=True, slots=True)
class SeededAccount:
    user_id: UUID
    credentials_id: UUID
    access_token: str


async def _seed_full_account(
    session: AsyncSession,
    *,
    subject: str,
    refresh_token_hash: str,
) -> SeededAccount:
    user = await create_persisted_user(
        session,
        name="탈퇴 테스트 사용자",
        email=f"{subject}@example.com",
    )
    from app.modules.users.domain.model import UserSettings

    settings = UserSettings.create(user_id=user.id)
    session.add(_settings_record(settings))
    credentials = await SqlAlchemyCredentialRepository(session).create_for_external_identity(
        identity=ExternalIdentity.create(
            issuer="google",
            subject=subject,
            provider="google",
            email=None if user.email is None else user.email.value,
            name=user.name,
        ),
        user_id=user.id,
        logged_in_at=datetime.now(UTC),
    )
    session_id = credentials.credentials_id
    session.add(
        auth_orm.AuthSession(
            id=session_id,
            credentials_id=credentials.credentials_id,
        )
    )
    session.add(
        credit_orm.UserCredit(
            user_id=user.id,
            feature_key="ocr",
            total_granted_count=5,
            used_count=1,
            remaining_count=4,
        )
    )
    session.add(
        credit_orm.CreditTransaction(
            user_id=user.id,
            feature_key="ocr",
            reason="monthlyOcrAllowance",
            action="grant",
            amount=5,
        )
    )
    await SqlAlchemyCredentialRepository(session).save_refresh_token(
        credentials_id=credentials.credentials_id,
        session_id=session_id,
        token_hash=refresh_token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    access_token = JwtAccessTokenService.from_settings(TEST_SETTINGS).issue(
        user_id=user.id,
        credentials_id=credentials.credentials_id,
        session_id=session_id,
        role=credentials.role.value,
    )
    await session.flush()
    return SeededAccount(
        user_id=user.id,
        credentials_id=credentials.credentials_id,
        access_token=access_token.token,
    )


def _settings_record(settings: object) -> users_orm.UserSettings:
    from app.modules.users.domain.model import UserSettings as DomainSettings

    assert isinstance(settings, DomainSettings)
    # UserSettings.id == user_id (entity PK is the user_id)
    return users_orm.UserSettings(
        user_id=settings.id,
    )


async def _count_all_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    async with session_factory() as session:
        users_count = await count_persisted_users(session)
        credentials_count = await session.scalar(
            select(func.count()).select_from(auth_orm.UserCredential)
        )
        identities_count = await session.scalar(
            select(func.count()).select_from(auth_orm.ExternalIdentity)
        )
        auth_sessions_count = await session.scalar(
            select(func.count()).select_from(auth_orm.AuthSession)
        )
        refresh_tokens_count = await session.scalar(
            select(func.count()).select_from(auth_orm.RefreshToken)
        )
        settings_count = await session.scalar(
            select(func.count()).select_from(users_orm.UserSettings)
        )
        user_credits_count = await session.scalar(
            select(func.count()).select_from(credit_orm.UserCredit)
        )
        credit_transactions_count = await session.scalar(
            select(func.count()).select_from(credit_orm.CreditTransaction)
        )

    def _req(v: int | None) -> int:
        if v is None:
            raise AssertionError("PostgreSQL COUNT returned no value")
        return v

    return {
        "users": users_count,
        "user_credentials": _req(credentials_count),
        "external_identities": _req(identities_count),
        "auth_sessions": _req(auth_sessions_count),
        "refresh_tokens": _req(refresh_tokens_count),
        "user_settings": _req(settings_count),
        "user_credits": _req(user_credits_count),
        "credit_transactions": _req(credit_transactions_count),
    }


@asynccontextmanager
async def _plain_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    test_app = create_app(TEST_SETTINGS)
    test_app.state.session_factory = session_factory

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


@asynccontextmanager
async def _client_with_failing_cleanup(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """Inject a failing users cleanup into the REAL withdraw use case so the REAL
    request transaction must roll back the auth delete atomically (no fake use case)."""

    class _FailingWithdrawalCleanup(WithdrawalCleanupCommandUseCase):
        def __init__(self) -> None:
            pass

        async def execute(self, command: WithdrawalCleanupCommand) -> None:
            raise RuntimeError("users cleanup failed (injected failure)")

    test_app = create_app(TEST_SETTINGS)
    test_app.state.session_factory = session_factory
    test_app.dependency_overrides[get_withdrawal_cleanup_command_use_case] = lambda: (
        _FailingWithdrawalCleanup()
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_delete_me_requires_bearer_token(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _plain_client(postgres_session_factory) as client:
        response = await client.delete("/api/v1/users/me")
        invalid_response = await client.delete(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid-token"},
        )

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["data"]["path"] == "/api/v1/users/me"

    invalid_body = invalid_response.json()
    assert invalid_response.status_code == 401
    assert invalid_body["success"] is False
    assert invalid_body["data"]["path"] == "/api/v1/users/me"


async def test_delete_me_withdraws_full_account(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Happy path: DELETE /api/v1/users/me removes ALL owned rows; second account untouched."""
    async with postgres_session_factory() as session, session.begin():
        current = await _seed_full_account(
            session,
            subject="current-user",
            refresh_token_hash="current-refresh-hash",
        )
        other = await _seed_full_account(
            session,
            subject="other-user",
            refresh_token_hash="other-refresh-hash",
        )

    async with _plain_client(postgres_session_factory) as client:
        response = await client.delete(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {current.access_token}"},
        )
        # stale token reuse must 401
        stale_response = await client.delete(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {current.access_token}"},
        )

    assert response.status_code == 204
    assert response.content == b""
    assert stale_response.status_code == 401

    async with postgres_session_factory() as session:
        # current user row gone
        assert not await persisted_user_exists(session, current.user_id)
        # auth rows for current gone
        assert await session.get(auth_orm.UserCredential, current.credentials_id) is None
        current_identities = list(
            await session.scalars(
                select(auth_orm.ExternalIdentity).where(
                    auth_orm.ExternalIdentity.credentials_id == current.credentials_id
                )
            )
        )
        current_refresh_tokens = list(
            await session.scalars(
                select(auth_orm.RefreshToken).where(
                    auth_orm.RefreshToken.credentials_id == current.credentials_id
                )
            )
        )
        current_settings = await session.get(users_orm.UserSettings, current.user_id)
        current_credit = await session.get(
            credit_orm.UserCredit,
            {"user_id": current.user_id, "feature_key": "ocr"},
        )
        current_credit_transactions = list(
            await session.scalars(
                select(credit_orm.CreditTransaction).where(
                    credit_orm.CreditTransaction.user_id == current.user_id
                )
            )
        )

        assert current_identities == []
        assert current_refresh_tokens == []
        assert current_settings is None
        assert current_credit is None
        assert current_credit_transactions == []

        # other account fully intact
        assert await persisted_user_exists(session, other.user_id)
        assert await session.get(auth_orm.UserCredential, other.credentials_id) is not None
        other_identities = list(
            await session.scalars(
                select(auth_orm.ExternalIdentity).where(
                    auth_orm.ExternalIdentity.credentials_id == other.credentials_id
                )
            )
        )
        assert len(other_identities) == 1
        assert (
            await session.get(
                credit_orm.UserCredit,
                {"user_id": other.user_id, "feature_key": "ocr"},
            )
            is not None
        )

    counts = await _count_all_rows(postgres_session_factory)
    assert counts == {
        "users": 1,
        "user_credentials": 1,
        "external_identities": 1,
        "auth_sessions": 1,
        "refresh_tokens": 1,
        "user_settings": 1,
        "user_credits": 1,
        "credit_transactions": 1,
    }


async def test_delete_me_rolls_back_when_users_cleanup_fails(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Rollback path: failing users cleanup -> 500; ALL rows (auth + users + push tokens) intact."""
    async with postgres_session_factory() as session, session.begin():
        current = await _seed_full_account(
            session,
            subject="rollback-user",
            refresh_token_hash="rollback-refresh-hash",
        )

    async with _client_with_failing_cleanup(postgres_session_factory) as client:
        response = await client.delete(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {current.access_token}"},
        )

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["status"] == 500
    assert body["data"]["message"] == "서버 내부 오류가 발생했습니다."
    assert body["data"]["path"] == "/api/v1/users/me"

    counts = await _count_all_rows(postgres_session_factory)
    assert counts == {
        "users": 1,
        "user_credentials": 1,
        "external_identities": 1,
        "auth_sessions": 1,
        "refresh_tokens": 1,
        "user_settings": 1,
        "user_credits": 1,
        "credit_transactions": 1,
    }, f"Expected all rows intact after rollback but got: {counts}"
