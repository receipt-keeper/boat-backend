from dataclasses import dataclass
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.unit_of_work import DeferredCommitUnitOfWork, UnitOfWork
from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.modules.auth.application.commands.signup.command import SignupCommand
from app.modules.auth.application.commands.signup.use_case import SignupCommandUseCase
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.application.ports.notification_settings_initializer import (
    NotificationSettingsInitializer,
)
from app.modules.auth.dependencies import (
    ProvisionUserPortAdapter,
    SignupPromotionRedeemerAdapter,
    build_auth_event_registry,
)
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.tests.service_fakes import (
    NoOpExternalIdentityLoginSynchronizer,
    build_access_token_issuer,
    build_promotion_beneficiary_key_factory,
    build_refresh_token_service,
)
from app.modules.credits.infrastructure.persistence import orm as credits_orm
from app.modules.promotions.dependencies import (
    build_redeem_signup_promotion_command_use_case,
)
from app.modules.promotions.infrastructure.persistence import orm as promotions_orm
from app.modules.promotions.tests.signup_promotion_test_support import (
    count_rows,
    seed_active_signup_campaign,
)
from app.modules.users.dependencies import build_resolve_user_for_login_command_use_case


class _InjectedCommitFailure(Exception):
    pass


class _FixedExternalIdentityVerifier(ExternalIdentityVerifier):
    async def verify(self, provider_token: str) -> ExternalIdentity:
        assert provider_token
        return ExternalIdentity.create(
            issuer="google",
            subject="failed-outer-commit",
            provider="google",
            email="failed-outer-commit@example.com",
            name="원자성 테스트 사용자",
            email_verified=True,
        )


@dataclass(slots=True)
class _FailingOuterUnitOfWork(UnitOfWork):
    session: AsyncSession
    commit_count: int = 0
    rollback_count: int = 0

    async def commit(self) -> None:
        self.commit_count += 1
        await self.session.flush()
        raise _InjectedCommitFailure("injected outer commit failure")

    async def rollback(self) -> None:
        self.rollback_count += 1
        await self.session.rollback()


class _NoOpNotificationSettingsInitializer(NotificationSettingsInitializer):
    async def initialize(self, *, user_id: UUID, marketing_consent: bool) -> None:
        assert user_id
        assert not marketing_consent


def _build_signup_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> SignupCommandUseCase:
    return SignupCommandUseCase(
        identity_verifier=_FixedExternalIdentityVerifier(),
        identity_synchronizer=NoOpExternalIdentityLoginSynchronizer(),
        credential_repository=SqlAlchemyCredentialRepository(session),
        user_provisioner=ProvisionUserPortAdapter(
            build_resolve_user_for_login_command_use_case(
                session,
                DeferredCommitUnitOfWork(),
            )
        ),
        notification_settings_initializer=_NoOpNotificationSettingsInitializer(),
        signup_promotion_redeemer=SignupPromotionRedeemerAdapter(
            command_use_case=build_redeem_signup_promotion_command_use_case(
                session,
                DeferredCommitUnitOfWork(),
            ),
            beneficiary_key_factory=build_promotion_beneficiary_key_factory(),
        ),
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=build_refresh_token_service(),
        unit_of_work=unit_of_work,
        event_publisher=OutboxEventPublisher(
            session=session,
            registry=build_auth_event_registry(),
        ),
    )


async def test_signup_rolls_back_promotion_credits_users_and_outbox_when_outer_commit_fails(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        promotion_id = await seed_active_signup_campaign(session, benefit_amount=5)
        unit_of_work = _FailingOuterUnitOfWork(session=session)

        with pytest.raises(_InjectedCommitFailure, match="injected outer commit failure"):
            await _build_signup_use_case(session, unit_of_work).execute(
                SignupCommand(
                    provider_token="redacted-provider-token",
                    terms_accepted=True,
                    privacy_accepted=True,
                    terms_version="2026-07-12",
                    privacy_version="2026-07-12",
                    marketing_consent=False,
                )
            )

    assert (unit_of_work.commit_count, unit_of_work.rollback_count) == (1, 1)
    async with postgres_session_factory() as session:
        promotion = await session.get(promotions_orm.Promotion, promotion_id)
        assert promotion is not None
        assert promotion.times_redeemed == 0
        assert await count_rows(session, auth_orm.UserCredential) == 0
        assert await count_rows(session, credits_orm.UserCredit) == 0
        assert await count_rows(session, credits_orm.CreditTransaction) == 0
        assert await count_rows(session, promotions_orm.PromotionRedemption) == 0
        assert await count_rows(session, OutboxEvent) == 0
