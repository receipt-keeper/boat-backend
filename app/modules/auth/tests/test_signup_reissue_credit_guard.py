"""credit-signup-abuse-guard 핵심 시나리오: signup → withdraw → 재signup 왕복에서
재가입 신원에는 가입 보너스 크레딧이 재지급되지 않음을 실제 컴포넌트(HMAC hasher +
SqlAlchemy tombstone registry + credits/users/notifications 실물 유스케이스)로 검증한다.

test_signup_event_atomicity.py/test_social_linking.py와 동일하게, FastAPI 앱 대신
실제 컴포넌트를 session에 직접 조립해 실행하는 통합 테스트 패턴을 따른다.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import DeferredCommitUnitOfWork
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.auth.application.commands.signup.command import SignupCommand
from app.modules.auth.application.commands.signup.use_case import SignupCommandUseCase
from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.application.commands.withdraw.use_case import WithdrawAccountCommandUseCase
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.dependencies import ProvisionUserPortAdapter, build_auth_event_registry
from app.modules.auth.dependency_adapters import (
    CreditInitializerAdapter,
    CreditWithdrawalCleanerAdapter,
    NotificationSettingsInitializerAdapter,
    PushTokenWithdrawalCleanerAdapter,
)
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.persistence.external_identity_login_synchronizer import (
    SqlAlchemyExternalIdentityLoginSynchronizer,
)
from app.modules.auth.infrastructure.persistence.withdrawn_identity_repository import (
    SqlAlchemyWithdrawnIdentityRegistry,
)
from app.modules.auth.infrastructure.security.identity_hasher import HmacIdentityHasher
from app.modules.auth.tests.service_fakes import (
    build_access_token_issuer,
    build_refresh_token_service,
)
from app.modules.credits.dependencies import (
    build_delete_user_credits_command_use_case,
    build_grant_credit_command_use_case,
)
from app.modules.credits.infrastructure.persistence import orm as credit_orm
from app.modules.notifications.dependencies import (
    build_delete_user_push_tokens_command_use_case,
    build_update_notification_settings_command_use_case,
)
from app.modules.users.dependencies import (
    build_resolve_user_for_login_command_use_case,
    build_withdrawal_cleanup_command_use_case,
)

TEST_IDENTITY_HASH_SECRET = "reissue-guard-test-identity-hash-secret"  # noqa: S105
RETENTION_DAYS = 180


class _FixedExternalIdentityVerifier(ExternalIdentityVerifier):
    def __init__(self, identity: ExternalIdentity) -> None:
        self._identity = identity

    async def verify(self, provider_token: str) -> ExternalIdentity:
        assert provider_token
        return self._identity


def _new_identity() -> ExternalIdentity:
    return ExternalIdentity.create(
        issuer="google",
        subject="reissue-guard-subject",
        provider="google",
        email="reissue-guard@example.com",
        name="재가입 가드 테스트 사용자",
        email_verified=True,
    )


def _signup_command() -> SignupCommand:
    return SignupCommand(
        provider_token="reissue-guard-token",
        terms_accepted=True,
        privacy_accepted=True,
        terms_version="2026-01-01",
        privacy_version="2026-01-01",
        marketing_consent=False,
    )


def _build_signup_use_case(
    *,
    session: AsyncSession,
    event_publisher: EventPublisher,
    identity: ExternalIdentity,
) -> SignupCommandUseCase:
    return SignupCommandUseCase(
        identity_verifier=_FixedExternalIdentityVerifier(identity),
        identity_synchronizer=SqlAlchemyExternalIdentityLoginSynchronizer(session),
        credential_repository=SqlAlchemyCredentialRepository(session),
        user_provisioner=ProvisionUserPortAdapter(
            build_resolve_user_for_login_command_use_case(session, DeferredCommitUnitOfWork())
        ),
        notification_settings_initializer=NotificationSettingsInitializerAdapter(
            build_update_notification_settings_command_use_case(session, DeferredCommitUnitOfWork())
        ),
        credit_initializer=CreditInitializerAdapter(
            build_grant_credit_command_use_case(session, DeferredCommitUnitOfWork())
        ),
        identity_hasher=HmacIdentityHasher(secret=TEST_IDENTITY_HASH_SECRET),
        withdrawn_identity_registry=SqlAlchemyWithdrawnIdentityRegistry(
            session,
            retention_days=RETENTION_DAYS,
        ),
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=build_refresh_token_service(),
        unit_of_work=SqlAlchemyUnitOfWork(session),
        event_publisher=event_publisher,
    )


def _build_withdraw_use_case(
    *,
    session: AsyncSession,
    event_publisher: EventPublisher,
) -> WithdrawAccountCommandUseCase:
    return WithdrawAccountCommandUseCase(
        credential_repository=SqlAlchemyCredentialRepository(session),
        withdrawal_cleanup_command_use_case=build_withdrawal_cleanup_command_use_case(
            session, DeferredCommitUnitOfWork()
        ),
        credit_withdrawal_cleaner=CreditWithdrawalCleanerAdapter(
            build_delete_user_credits_command_use_case(session, DeferredCommitUnitOfWork())
        ),
        push_token_withdrawal_cleaner=PushTokenWithdrawalCleanerAdapter(
            build_delete_user_push_tokens_command_use_case(session, DeferredCommitUnitOfWork())
        ),
        identity_hasher=HmacIdentityHasher(secret=TEST_IDENTITY_HASH_SECRET),
        withdrawn_identity_registry=SqlAlchemyWithdrawnIdentityRegistry(
            session,
            retention_days=RETENTION_DAYS,
        ),
        unit_of_work=SqlAlchemyUnitOfWork(session),
        event_publisher=event_publisher,
    )


async def test_signup_withdraw_resignup_round_trip_blocks_second_bonus_grant(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = _new_identity()

    # 1차 가입: 정상적으로 가입 보너스가 지급된다.
    async with postgres_session_factory() as session:
        event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_auth_event_registry(),
        )
        use_case = _build_signup_use_case(
            session=session,
            event_publisher=event_publisher,
            identity=identity,
        )
        first_result = await use_case.execute(_signup_command())
        first_credentials = await SqlAlchemyCredentialRepository(session).find_by_external_identity(
            identity=identity,
        )
    assert first_credentials is not None
    first_user_id = first_credentials.user_id
    first_credentials_id = first_credentials.credentials_id

    # 탈퇴 전: 1차 가입 보너스가 정상 지급되었는지 먼저 확인한다(탈퇴 시
    # credit_transactions/user_credits가 함께 삭제되므로 탈퇴 이후에는 확인할 수 없다).
    async with postgres_session_factory() as session:
        first_user_credit = await session.get(
            credit_orm.UserCredit,
            {"user_id": first_user_id, "feature_key": "ocr"},
        )
    assert first_user_credit is not None
    assert first_user_credit.total_granted_count == 5

    # 탈퇴: 연결된 identity 해시가 tombstone에 기록되고 계정이 삭제된다.
    async with postgres_session_factory() as session:
        event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_auth_event_registry(),
        )
        use_case = _build_withdraw_use_case(session=session, event_publisher=event_publisher)
        await use_case.execute(
            WithdrawAccountCommand(
                user_id=first_user_id,
                credentials_id=first_credentials_id,
            )
        )

    # 2차 가입: 동일 신원으로 재가입 - 계정은 새로 생성되지만 보너스는 재지급되지 않는다.
    async with postgres_session_factory() as session:
        event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_auth_event_registry(),
        )
        use_case = _build_signup_use_case(
            session=session,
            event_publisher=event_publisher,
            identity=identity,
        )
        second_result = await use_case.execute(_signup_command())
        second_credentials = await SqlAlchemyCredentialRepository(
            session
        ).find_by_external_identity(identity=identity)
    assert second_credentials is not None
    second_user_id = second_credentials.user_id

    # 새 user_id로 계정이 재발급된다(탈퇴 시 이전 계정은 완전히 삭제됨).
    assert second_user_id != first_user_id
    assert second_result.access_token
    assert second_result.access_token != first_result.access_token

    async with postgres_session_factory() as session:
        # 1차 계정의 credit_transactions/user_credits는 탈퇴 cleanup으로 이미 삭제되었고,
        # 2차 계정에는 애초에 grant가 없었으므로 이 시점에는 credit_transactions가 0건이어야
        # 한다 - 재가입에서 두 번째 grant가 발생하지 않았음을 증명하는 핵심 불변식이다.
        remaining_grant_count = await session.scalar(
            select(func.count()).select_from(credit_orm.CreditTransaction)
        )
        withdrawn_identity_row_count = await session.scalar(
            select(func.count()).select_from(auth_orm.WithdrawnIdentity)
        )
        second_user_credit = await session.get(
            credit_orm.UserCredit,
            {"user_id": second_user_id, "feature_key": "ocr"},
        )

    # 2차 grant는 발생하지 않았다(1차분은 탈퇴로 삭제, 2차분은 애초에 지급되지 않음).
    assert remaining_grant_count == 0
    # tombstone은 1회 기록된 상태로 남는다.
    assert withdrawn_identity_row_count == 1
    # 2차 계정에는 크레딧이 지급되지 않았다(UserCredit row 자체가 없음).
    assert second_user_credit is None


async def test_first_time_signup_grants_bonus_with_idempotency_key(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = ExternalIdentity.create(
        issuer="google",
        subject="first-time-signup-subject",
        provider="google",
        email="first-time-signup@example.com",
        name="최초 가입 테스트 사용자",
        email_verified=True,
    )

    async with postgres_session_factory() as session:
        event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_auth_event_registry(),
        )
        use_case = _build_signup_use_case(
            session=session,
            event_publisher=event_publisher,
            identity=identity,
        )
        await use_case.execute(_signup_command())
        credentials = await SqlAlchemyCredentialRepository(session).find_by_external_identity(
            identity=identity,
        )
    assert credentials is not None

    identity_hash = HmacIdentityHasher(secret=TEST_IDENTITY_HASH_SECRET).hash(
        issuer=identity.issuer.value,
        subject=identity.subject.value,
    )
    async with postgres_session_factory() as session:
        grant_rows = list(
            await session.scalars(
                select(credit_orm.CreditTransaction).where(
                    credit_orm.CreditTransaction.idempotency_key == f"signup-bonus:{identity_hash}"
                )
            )
        )
        user_credit = await session.get(
            credit_orm.UserCredit,
            {"user_id": credentials.user_id, "feature_key": "ocr"},
        )

    assert len(grant_rows) == 1
    assert grant_rows[0].user_id == credentials.user_id
    assert grant_rows[0].amount == 5
    assert user_credit is not None
    assert user_credit.total_granted_count == 5
