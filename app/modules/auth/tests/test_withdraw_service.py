from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.application.event_publisher import EventPublisher
from app.core.domain.events import DomainEvent
from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.application.commands.withdraw.use_case import WithdrawAccountCommandUseCase
from app.modules.auth.application.ports.benefit_subject_handle import (
    BenefitSubjectHandleProvider,
)
from app.modules.auth.application.ports.credit_lifecycle import CreditWithdrawalCleaner
from app.modules.auth.application.ports.push_token_lifecycle import PushTokenWithdrawalCleaner
from app.modules.auth.domain.model import ExternalIdentity, UserCredential
from app.modules.auth.tests.credential_repository_fake import FakeCredentialRepository
from app.modules.users.application.commands.withdrawal_cleanup.command import (
    WithdrawalCleanupCommand,
)
from app.modules.users.application.commands.withdrawal_cleanup.use_case import (
    WithdrawalCleanupCommandUseCase,
)
from tests.support.unit_of_work import FakeUnitOfWork


class RecordingEventPublisher(EventPublisher):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    async def publish(self, events: Sequence[DomainEvent]) -> None:
        self.published.extend(events)


class NoOpWithdrawalCleanupCommandUseCase(WithdrawalCleanupCommandUseCase):
    def __init__(self) -> None:  # 실물 의존성 없이 호출만 기록하는 테스트 더블
        self.executed_user_ids: list[UUID] = []

    async def execute(self, command: WithdrawalCleanupCommand) -> None:
        self.executed_user_ids.append(command.user_id)


@dataclass(frozen=True, slots=True)
class DeletedCreditAccountState:
    user_id: UUID
    candidate_handles: tuple[str, ...]


class RecordingCreditWithdrawalCleaner(CreditWithdrawalCleaner):
    def __init__(self) -> None:
        self.calls: list[DeletedCreditAccountState] = []

    async def delete_account_state(
        self,
        *,
        user_id: UUID,
        candidate_handles: Sequence[str],
    ) -> None:
        self.calls.append(
            DeletedCreditAccountState(user_id=user_id, candidate_handles=tuple(candidate_handles))
        )


class RecordingPushTokenWithdrawalCleaner(PushTokenWithdrawalCleaner):
    def __init__(self) -> None:
        self.deleted_user_ids: list[UUID] = []

    async def delete_account_state(self, *, user_id: UUID) -> None:
        self.deleted_user_ids.append(user_id)


class FakeBenefitSubjectHandleProvider(BenefitSubjectHandleProvider):
    def handle(self, *, subject: str) -> str:
        return f"handle:{subject}"

    def candidate_handles(self, *, subject: str) -> Sequence[str]:
        return [self.handle(subject=subject), f"retired-handle:{subject}"]


@dataclass(frozen=True, slots=True)
class WithdrawUseCaseFixture:
    use_case: WithdrawAccountCommandUseCase
    repository: FakeCredentialRepository
    withdrawal_cleanup: NoOpWithdrawalCleanupCommandUseCase
    credit_cleaner: RecordingCreditWithdrawalCleaner
    push_token_cleaner: RecordingPushTokenWithdrawalCleaner
    unit_of_work: FakeUnitOfWork
    event_publisher: RecordingEventPublisher


def _build_withdraw_use_case() -> WithdrawUseCaseFixture:
    repository = FakeCredentialRepository()
    withdrawal_cleanup = NoOpWithdrawalCleanupCommandUseCase()
    credit_cleaner = RecordingCreditWithdrawalCleaner()
    push_token_cleaner = RecordingPushTokenWithdrawalCleaner()
    unit_of_work = FakeUnitOfWork()
    event_publisher = RecordingEventPublisher()
    return WithdrawUseCaseFixture(
        use_case=WithdrawAccountCommandUseCase(
            credential_repository=repository,
            withdrawal_cleanup_command_use_case=withdrawal_cleanup,
            credit_withdrawal_cleaner=credit_cleaner,
            push_token_withdrawal_cleaner=push_token_cleaner,
            benefit_subject_handle_provider=FakeBenefitSubjectHandleProvider(),
            unit_of_work=unit_of_work,
            event_publisher=event_publisher,
        ),
        repository=repository,
        withdrawal_cleanup=withdrawal_cleanup,
        credit_cleaner=credit_cleaner,
        push_token_cleaner=push_token_cleaner,
        unit_of_work=unit_of_work,
        event_publisher=event_publisher,
    )


async def test_withdraw_computes_candidate_handles_from_first_linked_identity() -> None:
    fixture = _build_withdraw_use_case()
    user_id = uuid4()
    credentials = UserCredential.create(user_id=user_id, credentials_id=uuid4(), role="user")
    google_identity = ExternalIdentity.create(
        issuer="google",
        subject="shared-firebase-uid",
        provider="google",
        email="user@example.com",
        name="테스트 사용자",
        email_verified=True,
    )
    fixture.repository.seed_existing_external_identity(
        identity=google_identity,
        credentials=credentials,
    )

    await fixture.use_case.execute(
        WithdrawAccountCommand(
            user_id=credentials.user_id,
            credentials_id=credentials.credentials_id,
        )
    )

    assert fixture.credit_cleaner.calls == [
        DeletedCreditAccountState(
            user_id=user_id,
            candidate_handles=(
                "handle:shared-firebase-uid",
                "retired-handle:shared-firebase-uid",
            ),
        )
    ]
    # 삭제(delete_account_auth_state)는 handle 계산 이후에 일어난다.
    assert fixture.repository.credentials_by_identity == {}
    assert fixture.withdrawal_cleanup.executed_user_ids == [user_id]
    assert fixture.push_token_cleaner.deleted_user_ids == [user_id]
    assert fixture.unit_of_work.commit_count == 1
    assert len(fixture.event_publisher.published) == 1


async def test_withdraw_uses_only_first_linked_identity_when_socially_linked() -> None:
    """소셜 링크된 identity는 모두 같은 Firebase uid를 공유하므로 첫 row의 subject만
    쓴다 - 여러 issuer(google/apple)가 연결돼 있어도 handle 계산은 한 번뿐이다."""
    fixture = _build_withdraw_use_case()
    user_id = uuid4()
    credentials = UserCredential.create(user_id=user_id, credentials_id=uuid4(), role="user")
    google_identity = ExternalIdentity.create(
        issuer="google",
        subject="shared-firebase-uid",
        provider="google",
        email="user@example.com",
        name="테스트 사용자",
        email_verified=True,
    )
    apple_identity = ExternalIdentity.create(
        issuer="apple",
        subject="shared-firebase-uid",
        provider="apple",
        email=None,
        name=None,
    )
    fixture.repository.seed_existing_external_identity(
        identity=google_identity,
        credentials=credentials,
    )
    fixture.repository.seed_existing_external_identity(
        identity=apple_identity,
        credentials=credentials,
    )

    await fixture.use_case.execute(
        WithdrawAccountCommand(
            user_id=credentials.user_id,
            credentials_id=credentials.credentials_id,
        )
    )

    assert len(fixture.credit_cleaner.calls) == 1
    assert fixture.credit_cleaner.calls[0].candidate_handles == (
        "handle:shared-firebase-uid",
        "retired-handle:shared-firebase-uid",
    )


async def test_withdraw_with_no_linked_identities_passes_empty_candidate_handles() -> None:
    fixture = _build_withdraw_use_case()
    user_id = uuid4()
    credentials_id = uuid4()

    await fixture.use_case.execute(
        WithdrawAccountCommand(user_id=user_id, credentials_id=credentials_id)
    )

    assert fixture.credit_cleaner.calls == [
        DeletedCreditAccountState(user_id=user_id, candidate_handles=())
    ]
    assert fixture.withdrawal_cleanup.executed_user_ids == [user_id]
    assert fixture.unit_of_work.commit_count == 1
