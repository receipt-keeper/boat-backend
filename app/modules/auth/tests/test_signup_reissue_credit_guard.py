"""credit-signup-abuse-guard 핵심 시나리오: signup -> withdraw -> re-signup 왕복에서
재가입 신원에 가입 보너스 크레딧이 재지급되지 않고, claim(credit_transactions의
signup-allowance row)이 보존 기간 동안 재활성화 가능한 상태로 남음을 실제 컴포넌트
(HMAC handle provider + credits 실물 use case + users/notifications 실물 유스케이스)로
검증한다.

test_signup_event_atomicity.py/test_social_linking.py와 동일하게, FastAPI 앱 대신 실제
컴포넌트를 session에 직접 조립해 실행하는 통합 테스트 패턴을 따른다.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import DeferredCommitUnitOfWork
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.auth.application.commands.signup.command import SignupCommand
from app.modules.auth.application.commands.signup.result import SignupResult
from app.modules.auth.application.commands.signup.use_case import SignupCommandUseCase
from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.application.commands.withdraw.use_case import WithdrawAccountCommandUseCase
from app.modules.auth.application.ports.benefit_subject_handle import (
    BenefitSubjectHandleProvider,
)
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.dependencies import ProvisionUserPortAdapter, build_auth_event_registry
from app.modules.auth.dependency_adapters import (
    CreditInitializerAdapter,
    CreditWithdrawalCleanerAdapter,
    NotificationSettingsInitializerAdapter,
    PushTokenWithdrawalCleanerAdapter,
)
from app.modules.auth.domain.model import ExternalIdentity, UserCredential
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.persistence.external_identity_login_synchronizer import (
    SqlAlchemyExternalIdentityLoginSynchronizer,
)
from app.modules.auth.infrastructure.security.identity_hasher import (
    HmacBenefitSubjectHandleProvider,
)
from app.modules.auth.tests.service_fakes import (
    build_access_token_issuer,
    build_refresh_token_service,
)
from app.modules.credits.dependencies import (
    build_close_credit_account_command_use_case,
    build_issue_signup_allowance_command_use_case,
)
from app.modules.credits.infrastructure.persistence import orm as credit_orm
from app.modules.credits.infrastructure.persistence.claim_purger import CreditClaimPurger
from app.modules.notifications.dependencies import (
    build_delete_user_push_tokens_command_use_case,
    build_update_notification_settings_command_use_case,
)
from app.modules.users.dependencies import (
    build_resolve_user_for_login_command_use_case,
    build_withdrawal_cleanup_command_use_case,
)

TEST_NAMESPACE = "reissue-guard-namespace"
RETENTION_DAYS = 180
TEST_IDENTITY_HASH_SECRET_V1 = "reissue-guard-test-identity-hash-secret-v1"  # noqa: S105
TEST_IDENTITY_HASH_SECRET_V2 = "reissue-guard-test-identity-hash-secret-v2"  # noqa: S105


def _v1_handle_provider() -> HmacBenefitSubjectHandleProvider:
    return HmacBenefitSubjectHandleProvider(
        namespace=TEST_NAMESPACE,
        current_version="v1",
        current_secret=TEST_IDENTITY_HASH_SECRET_V1,
    )


def _rotated_handle_provider() -> HmacBenefitSubjectHandleProvider:
    """v2가 현행, v1이 은퇴된 상태의 키 링 - 회전 시나리오 전용."""
    return HmacBenefitSubjectHandleProvider(
        namespace=TEST_NAMESPACE,
        current_version="v2",
        current_secret=TEST_IDENTITY_HASH_SECRET_V2,
        retired_secrets={"v1": TEST_IDENTITY_HASH_SECRET_V1},
    )


class _FixedExternalIdentityVerifier(ExternalIdentityVerifier):
    def __init__(self, identity: ExternalIdentity) -> None:
        self._identity = identity

    async def verify(self, provider_token: str) -> ExternalIdentity:
        assert provider_token
        return self._identity


def _identity(*, issuer: str = "google", subject: str, email: str) -> ExternalIdentity:
    return ExternalIdentity.create(
        issuer=issuer,
        subject=subject,
        provider=issuer,
        email=email,
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
    handle_provider: BenefitSubjectHandleProvider,
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
            build_issue_signup_allowance_command_use_case(session, DeferredCommitUnitOfWork())
        ),
        benefit_subject_handle_provider=handle_provider,
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=build_refresh_token_service(),
        unit_of_work=SqlAlchemyUnitOfWork(session),
        event_publisher=event_publisher,
    )


def _build_withdraw_use_case(
    *,
    session: AsyncSession,
    event_publisher: EventPublisher,
    handle_provider: BenefitSubjectHandleProvider,
) -> WithdrawAccountCommandUseCase:
    return WithdrawAccountCommandUseCase(
        credential_repository=SqlAlchemyCredentialRepository(session),
        withdrawal_cleanup_command_use_case=build_withdrawal_cleanup_command_use_case(
            session, DeferredCommitUnitOfWork()
        ),
        credit_withdrawal_cleaner=CreditWithdrawalCleanerAdapter(
            build_close_credit_account_command_use_case(
                session,
                DeferredCommitUnitOfWork(),
                retention_days=RETENTION_DAYS,
            )
        ),
        push_token_withdrawal_cleaner=PushTokenWithdrawalCleanerAdapter(
            build_delete_user_push_tokens_command_use_case(session, DeferredCommitUnitOfWork())
        ),
        benefit_subject_handle_provider=handle_provider,
        unit_of_work=SqlAlchemyUnitOfWork(session),
        event_publisher=event_publisher,
    )


async def _signup(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    identity: ExternalIdentity,
    handle_provider: BenefitSubjectHandleProvider,
) -> tuple[SignupResult, UserCredential]:
    async with session_factory() as session:
        event_publisher = OutboxEventPublisher(
            session=session, registry=build_auth_event_registry()
        )
        use_case = _build_signup_use_case(
            session=session,
            event_publisher=event_publisher,
            identity=identity,
            handle_provider=handle_provider,
        )
        result = await use_case.execute(_signup_command())
        credentials = await SqlAlchemyCredentialRepository(session).find_by_external_identity(
            identity=identity,
        )
    assert credentials is not None
    return result, credentials


async def _withdraw(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    credentials_id: UUID,
    handle_provider: BenefitSubjectHandleProvider,
) -> None:
    async with session_factory() as session:
        event_publisher = OutboxEventPublisher(
            session=session, registry=build_auth_event_registry()
        )
        use_case = _build_withdraw_use_case(
            session=session,
            event_publisher=event_publisher,
            handle_provider=handle_provider,
        )
        await use_case.execute(
            WithdrawAccountCommand(user_id=user_id, credentials_id=credentials_id)
        )


async def _signup_allowance_transactions(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[credit_orm.CreditTransaction]:
    async with session_factory() as session:
        rows = list(
            await session.scalars(
                select(credit_orm.CreditTransaction).where(
                    credit_orm.CreditTransaction.idempotency_key.like("signup-allowance:%")
                )
            )
        )
    return rows


async def test_signup_withdraw_resignup_round_trip_blocks_regrant_and_reactivates_claim(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """시나리오 1: 가입 -> 탈퇴 -> 재가입 왕복 - 재지급 0, claim row 잔존 +
    재가입 후 purge_after IS NULL(재활성화), 새 user_id 정상."""
    identity = _identity(subject="round-trip-subject", email="round-trip@example.com")
    handle_provider = _v1_handle_provider()

    first_result, first_credentials = await _signup(
        postgres_session_factory, identity=identity, handle_provider=handle_provider
    )
    first_user_id = first_credentials.user_id
    first_credentials_id = first_credentials.credentials_id

    async with postgres_session_factory() as session:
        first_user_credit = await session.get(
            credit_orm.UserCredit, {"user_id": first_user_id, "feature_key": "ocr"}
        )
    assert first_user_credit is not None
    assert first_user_credit.total_granted_count == 5

    await _withdraw(
        postgres_session_factory,
        user_id=first_user_id,
        credentials_id=first_credentials_id,
        handle_provider=handle_provider,
    )

    # 탈퇴 직후: claim row는 삭제되지 않고 purge_after가 채워진 채 잔존한다.
    claims_after_withdraw = await _signup_allowance_transactions(postgres_session_factory)
    assert len(claims_after_withdraw) == 1
    assert claims_after_withdraw[0].purge_after is not None

    second_result, second_credentials = await _signup(
        postgres_session_factory, identity=identity, handle_provider=handle_provider
    )
    second_user_id = second_credentials.user_id

    # 새 user_id로 계정이 재발급된다(탈퇴 시 이전 계정은 완전히 삭제됨).
    assert second_user_id != first_user_id
    assert second_result.access_token
    assert second_result.access_token != first_result.access_token

    async with postgres_session_factory() as session:
        second_user_credit = await session.get(
            credit_orm.UserCredit, {"user_id": second_user_id, "feature_key": "ocr"}
        )
    # 재지급 없음: 새 계정에는 크레딧 잔액이 지급되지 않는다.
    assert second_user_credit is None

    claims_after_resignup = await _signup_allowance_transactions(postgres_session_factory)
    assert len(claims_after_resignup) == 1
    assert claims_after_resignup[0].id == claims_after_withdraw[0].id
    # 재활성화: 재가입으로 purge_after가 NULL로 되돌아간다.
    assert claims_after_resignup[0].purge_after is None


async def test_resignup_then_rewithdraw_resets_purge_after(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """시나리오 2: 재가입 후 재탈퇴 - purge_after가 다시 설정된다."""
    identity = _identity(subject="rewithdraw-subject", email="rewithdraw@example.com")
    handle_provider = _v1_handle_provider()

    _, first_credentials = await _signup(
        postgres_session_factory, identity=identity, handle_provider=handle_provider
    )
    await _withdraw(
        postgres_session_factory,
        user_id=first_credentials.user_id,
        credentials_id=first_credentials.credentials_id,
        handle_provider=handle_provider,
    )
    _, second_credentials = await _signup(
        postgres_session_factory, identity=identity, handle_provider=handle_provider
    )

    claims_after_reactivation = await _signup_allowance_transactions(postgres_session_factory)
    assert claims_after_reactivation[0].purge_after is None

    await _withdraw(
        postgres_session_factory,
        user_id=second_credentials.user_id,
        credentials_id=second_credentials.credentials_id,
        handle_provider=handle_provider,
    )

    claims_after_second_withdraw = await _signup_allowance_transactions(postgres_session_factory)
    assert len(claims_after_second_withdraw) == 1
    assert claims_after_second_withdraw[0].purge_after is not None
    assert claims_after_second_withdraw[0].purge_after > datetime.now(UTC)


async def test_resignup_after_claim_purged_grants_a_fresh_bonus(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """시나리오 3: purge 후 재가입 - 신규 claim + 5 지급(의도된 동작)."""
    identity = _identity(subject="purged-then-resignup-subject", email="purged@example.com")
    handle_provider = _v1_handle_provider()

    _, first_credentials = await _signup(
        postgres_session_factory, identity=identity, handle_provider=handle_provider
    )
    await _withdraw(
        postgres_session_factory,
        user_id=first_credentials.user_id,
        credentials_id=first_credentials.credentials_id,
        handle_provider=handle_provider,
    )

    # 보존 기간이 이미 지난 것처럼 파기 폴러를 미래 시각 clock으로 실행한다.
    async with postgres_session_factory() as session:
        deleted_count = await CreditClaimPurger(
            clock=lambda: datetime.now(UTC) + timedelta(days=181)
        ).run_once(session)
    assert deleted_count == 1
    assert await _signup_allowance_transactions(postgres_session_factory) == []

    _, second_credentials = await _signup(
        postgres_session_factory, identity=identity, handle_provider=handle_provider
    )

    async with postgres_session_factory() as session:
        second_user_credit = await session.get(
            credit_orm.UserCredit,
            {"user_id": second_credentials.user_id, "feature_key": "ocr"},
        )
    assert second_user_credit is not None
    assert second_user_credit.total_granted_count == 5

    claims_after_fresh_signup = await _signup_allowance_transactions(postgres_session_factory)
    assert len(claims_after_fresh_signup) == 1
    assert claims_after_fresh_signup[0].purge_after is None


async def test_switching_login_provider_with_same_uid_blocks_regrant(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """시나리오 4: google -> apple 전환(동일 firebase uid) - 동일 handle로 재지급 차단."""
    shared_uid = "shared-firebase-uid-provider-switch"
    handle_provider = _v1_handle_provider()

    google_identity = _identity(
        issuer="google", subject=shared_uid, email="provider-switch@example.com"
    )
    _, first_credentials = await _signup(
        postgres_session_factory, identity=google_identity, handle_provider=handle_provider
    )
    await _withdraw(
        postgres_session_factory,
        user_id=first_credentials.user_id,
        credentials_id=first_credentials.credentials_id,
        handle_provider=handle_provider,
    )

    apple_identity = ExternalIdentity.create(
        issuer="apple",
        subject=shared_uid,
        provider="apple",
        email=None,
        name="재가입 가드 테스트 사용자",
    )
    _, second_credentials = await _signup(
        postgres_session_factory, identity=apple_identity, handle_provider=handle_provider
    )

    async with postgres_session_factory() as session:
        second_user_credit = await session.get(
            credit_orm.UserCredit,
            {"user_id": second_credentials.user_id, "feature_key": "ocr"},
        )
    # 동일 uid이므로 issuer가 바뀌어도 같은 handle -> 재지급되지 않는다.
    assert second_user_credit is None

    claims = await _signup_allowance_transactions(postgres_session_factory)
    assert len(claims) == 1
    assert claims[0].purge_after is None


async def test_key_rotation_reactivates_prior_v1_claim_without_regrant(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """시나리오 5: 키 회전 - v1 키로 claim 생성 후 v2 현행 + v1 은퇴 체제에서 재가입 ->
    조회 후보에 은퇴 v1이 포함되어 히트하므로 무지급 재활성화."""
    identity = _identity(subject="key-rotation-subject", email="key-rotation@example.com")
    v1_provider = _v1_handle_provider()
    rotated_provider = _rotated_handle_provider()

    _, first_credentials = await _signup(
        postgres_session_factory, identity=identity, handle_provider=v1_provider
    )
    claims_before_withdraw = await _signup_allowance_transactions(postgres_session_factory)
    assert claims_before_withdraw[0].idempotency_key == (
        f"signup-allowance:{v1_provider.handle(subject=identity.subject.value)}"
    )

    # 탈퇴 시점에도 회전된 키 링을 쓴다 - candidate_handles에 v1이 포함되어 있어야
    # 기존 v1 claim을 정확히 찾아 purge_after를 설정할 수 있다.
    await _withdraw(
        postgres_session_factory,
        user_id=first_credentials.user_id,
        credentials_id=first_credentials.credentials_id,
        handle_provider=rotated_provider,
    )
    claims_after_withdraw = await _signup_allowance_transactions(postgres_session_factory)
    assert len(claims_after_withdraw) == 1
    assert claims_after_withdraw[0].purge_after is not None

    # 재가입 시점: 현행 키는 v2이지만 후보 목록의 은퇴 v1이 기존 claim과 일치한다.
    _, second_credentials = await _signup(
        postgres_session_factory, identity=identity, handle_provider=rotated_provider
    )

    async with postgres_session_factory() as session:
        second_user_credit = await session.get(
            credit_orm.UserCredit,
            {"user_id": second_credentials.user_id, "feature_key": "ocr"},
        )
    assert second_user_credit is None

    claims_after_resignup = await _signup_allowance_transactions(postgres_session_factory)
    assert len(claims_after_resignup) == 1
    # 여전히 v1 handle로 기록된 원래 row 그대로다(새 v2 row가 추가로 생기지 않는다).
    assert claims_after_resignup[0].idempotency_key == (
        f"signup-allowance:{v1_provider.handle(subject=identity.subject.value)}"
    )
    assert claims_after_resignup[0].purge_after is None
