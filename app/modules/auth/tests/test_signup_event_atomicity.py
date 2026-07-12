"""signup 1회 실행이 UserRegistered(users) + UserCredentialCreated(auth)를
같은 트랜잭션의 outbox row로 원자 커밋함을 증명하는 통합 테스트.

T6 (docs/domain-events/plan.md) 핵심 통합 테스트: real SqlAlchemyCredentialRepository +
real users ResolveUserForLoginCommandUseCase(=UserProvisioner 어댑터가 감싸는 실물)를
같은 세션으로 조립해, signup 성공 시 outbox row가 정확히 2건(UserRegistered 1 +
UserCredentialCreated 1) 남고, 실패 시나리오(중복 credential 유도)에서는 rollback으로
outbox row가 0건임을 검증한다.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import DeferredCommitUnitOfWork
from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.outbox.serialization import EventTypeRegistry
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.auth.application.commands.signup.command import SignupCommand
from app.modules.auth.application.commands.signup.use_case import SignupCommandUseCase
from app.modules.auth.application.ports.credit_lifecycle import CreditInitializer
from app.modules.auth.application.ports.notification_settings_initializer import (
    NotificationSettingsInitializer,
)
from app.modules.auth.application.ports.user_provisioner import (
    ProvisionedUser,
    UserProvisioner,
    UserProvisioningRequest,
)
from app.modules.auth.dependencies import ProvisionUserPortAdapter, build_auth_event_registry
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.security.identity_hasher import (
    HmacBenefitSubjectHandleProvider,
)
from app.modules.auth.tests.service_fakes import (
    NoOpExternalIdentityLoginSynchronizer,
    build_access_token_issuer,
    build_refresh_token_service,
)
from app.modules.users.dependencies import (
    build_resolve_user_for_login_command_use_case,
    build_users_event_registry,
)

TEST_IDENTITY_HASH_NAMESPACE = "atomicity-test-namespace"
TEST_IDENTITY_HASH_SECRET = "atomicity-test-identity-hash-secret"  # noqa: S105


class _NoOpCreditInitializer(CreditInitializer):
    async def initialize(
        self,
        *,
        user_id: UUID,
        subject_handle: str,
        candidate_handles: Sequence[str],
    ) -> None:
        assert user_id
        assert subject_handle
        assert candidate_handles


class _NoOpNotificationSettingsInitializer(NotificationSettingsInitializer):
    async def initialize(self, *, user_id: UUID, marketing_consent: bool) -> None:
        assert user_id
        assert marketing_consent in (True, False)


class _FixedUserIdProvisioner(UserProvisioner):
    """레이스 컨디션으로 이미 credential이 존재하는 user_id를 재사용하는 provisioner.

    실패 시나리오(중복 credential 제약 위반)를 결정론적으로 유도하기 위한 테스트 전용
    더블이다 — signup의 정상 `_ensure_new_user` 사전 체크는 통과하되, 실제 저장 시점에는
    이미 credential이 존재하는 user_id라 `user_credentials.user_id` unique 제약을 위반한다.
    """

    def __init__(self, *, user_id: UUID) -> None:
        self._user_id = user_id

    async def provision(self, *, request: UserProvisioningRequest) -> ProvisionedUser:
        return ProvisionedUser(user_id=self._user_id)


def _build_signup_use_case(
    *,
    session: AsyncSession,
    user_provisioner: UserProvisioner,
    event_publisher: EventPublisher,
    identity_verifier: object,
) -> SignupCommandUseCase:
    return SignupCommandUseCase(
        identity_verifier=identity_verifier,  # type: ignore[arg-type]
        identity_synchronizer=NoOpExternalIdentityLoginSynchronizer(),
        credential_repository=SqlAlchemyCredentialRepository(session),
        user_provisioner=user_provisioner,
        notification_settings_initializer=_NoOpNotificationSettingsInitializer(),
        credit_initializer=_NoOpCreditInitializer(),
        benefit_subject_handle_provider=HmacBenefitSubjectHandleProvider(
            namespace=TEST_IDENTITY_HASH_NAMESPACE,
            current_version="v1",
            current_secret=TEST_IDENTITY_HASH_SECRET,
        ),
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=build_refresh_token_service(),
        unit_of_work=SqlAlchemyUnitOfWork(session),
        event_publisher=event_publisher,
    )


def _merged_registry() -> EventTypeRegistry:
    registry = EventTypeRegistry()
    registry.merge(build_users_event_registry())
    registry.merge(build_auth_event_registry())
    return registry


async def _outbox_event_types(session: AsyncSession) -> list[str]:
    rows = list(await session.scalars(select(OutboxEvent.event_type).order_by(OutboxEvent.id)))
    return rows


async def _outbox_row_count(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(OutboxEvent))
    if count is None:
        raise AssertionError("PostgreSQL COUNT returned no value")
    return count


class _FakeExternalIdentityVerifier:
    def __init__(self, identity: ExternalIdentity) -> None:
        self._identity = identity

    async def verify(self, provider_token: str) -> ExternalIdentity:
        assert provider_token
        return self._identity


def _new_identity(*, subject: str) -> ExternalIdentity:
    return ExternalIdentity.create(
        issuer="google",
        subject=subject,
        provider="google",
        email=f"{subject}@example.com",
        name="원자성 테스트 사용자",
        email_verified=True,
    )


async def test_signup_commits_user_registered_and_user_credential_created_atomically(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = _new_identity(subject="atomic-signup-subject")

    async with postgres_session_factory() as session:
        registry = _merged_registry()
        assert registry.resolve("UserRegistered") is not None
        assert registry.resolve("UserCredentialCreated") is not None

        users_event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_users_event_registry(),
        )
        resolve_use_case = build_resolve_user_for_login_command_use_case(
            session,
            DeferredCommitUnitOfWork(),
        )
        # ResolveUserForLoginCommandUseCase는 users dependencies가 조립하는 실물이며
        # 이미 users 전용 OutboxEventPublisher를 내부에서 자체 조립한다(T5 선례).
        # 여기서는 그 실물을 그대로 UserProvisioner 어댑터로 감싼다.
        user_provisioner = ProvisionUserPortAdapter(resolve_use_case)

        auth_event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_auth_event_registry(),
        )
        use_case = _build_signup_use_case(
            session=session,
            user_provisioner=user_provisioner,
            event_publisher=auth_event_publisher,
            identity_verifier=_FakeExternalIdentityVerifier(identity),
        )

        result = await use_case.execute(
            SignupCommand(
                provider_token="atomic-signup-token",
                terms_accepted=True,
                privacy_accepted=True,
                terms_version="2026-01-01",
                privacy_version="2026-01-01",
                marketing_consent=False,
            )
        )
        assert result.access_token
        assert users_event_publisher  # 재사용 방지용 참조 유지(직접 발행하지 않음)

        event_types = await _outbox_event_types(session)

    assert sorted(event_types) == sorted(["UserRegistered", "UserCredentialCreated"])
    assert await _outbox_row_count(postgres_session_factory) == 2


async def test_signup_failure_rolls_back_outbox_rows_to_zero(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """중복 credential 제약 위반(user_credentials.user_id unique)으로 signup이
    실패하면, 같은 트랜잭션에 insert된 outbox row(UserRegistered 포함)도 rollback으로
    전부 소거되어야 한다."""
    colliding_user_id = uuid4()
    identity_for_seed = _new_identity(subject="rollback-seed-subject")
    identity_for_attempt = _new_identity(subject="rollback-attempt-subject")

    # 먼저 정상적으로 하나의 계정을 만들어 user_id에 credential을 선점시킨다.
    async with postgres_session_factory() as seed_session:
        seed_credentials = await SqlAlchemyCredentialRepository(
            seed_session
        ).create_for_external_identity(
            identity=identity_for_seed,
            user_id=colliding_user_id,
            logged_in_at=datetime.now(UTC),
        )
        assert seed_credentials.user_id == colliding_user_id
        await SqlAlchemyUnitOfWork(seed_session).commit()

    assert await _outbox_row_count(postgres_session_factory) == 0

    async with postgres_session_factory() as session:
        user_provisioner = _FixedUserIdProvisioner(user_id=colliding_user_id)
        auth_event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_auth_event_registry(),
        )
        use_case = _build_signup_use_case(
            session=session,
            user_provisioner=user_provisioner,
            event_publisher=auth_event_publisher,
            identity_verifier=_FakeExternalIdentityVerifier(identity_for_attempt),
        )

        raised: Exception | None = None
        try:
            await use_case.execute(
                SignupCommand(
                    provider_token="rollback-attempt-token",
                    terms_accepted=True,
                    privacy_accepted=True,
                    terms_version="2026-01-01",
                    privacy_version="2026-01-01",
                    marketing_consent=False,
                )
            )
        except (IntegrityError, SQLAlchemyError) as exc:
            raised = exc
            await session.rollback()

    assert raised is not None, "Expected IntegrityError from duplicate user_id credential"
    assert await _outbox_row_count(postgres_session_factory) == 0


async def test_signup_replay_free_happy_path_publishes_exactly_expected_event_types(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """이벤트 타입이 정확히 2종(UserRegistered, UserCredentialCreated)만 발행되고
    다른 타입(예: UserWithdrawn, AccountWithdrawn)은 섞이지 않음을 고정한다."""
    identity = _new_identity(subject="type-fidelity-subject")

    async with postgres_session_factory() as session:
        resolve_use_case = build_resolve_user_for_login_command_use_case(
            session,
            DeferredCommitUnitOfWork(),
        )
        user_provisioner = ProvisionUserPortAdapter(resolve_use_case)
        auth_event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_auth_event_registry(),
        )
        use_case = _build_signup_use_case(
            session=session,
            user_provisioner=user_provisioner,
            event_publisher=auth_event_publisher,
            identity_verifier=_FakeExternalIdentityVerifier(identity),
        )

        await use_case.execute(
            SignupCommand(
                provider_token="type-fidelity-token",
                terms_accepted=True,
                privacy_accepted=True,
                terms_version="2026-01-01",
                privacy_version="2026-01-01",
                marketing_consent=True,
            )
        )
        event_types = set(await _outbox_event_types(session))

    assert event_types == {"UserRegistered", "UserCredentialCreated"}
