from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.application.event_publisher import EventPublisher
from app.core.domain.events import DomainEvent
from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.application.commands.withdraw.use_case import WithdrawAccountCommandUseCase
from app.modules.auth.application.ports.credit_lifecycle import CreditWithdrawalCleaner
from app.modules.auth.application.ports.push_token_lifecycle import PushTokenWithdrawalCleaner
from app.modules.auth.application.ports.withdrawn_identity import (
    IdentityHasher,
    WithdrawnIdentityRegistry,
)
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


class RecordingCreditWithdrawalCleaner(CreditWithdrawalCleaner):
    def __init__(self) -> None:
        self.deleted_user_ids: list[UUID] = []

    async def delete_account_state(self, *, user_id: UUID) -> None:
        self.deleted_user_ids.append(user_id)


class RecordingPushTokenWithdrawalCleaner(PushTokenWithdrawalCleaner):
    def __init__(self) -> None:
        self.deleted_user_ids: list[UUID] = []

    async def delete_account_state(self, *, user_id: UUID) -> None:
        self.deleted_user_ids.append(user_id)


class FakeIdentityHasher(IdentityHasher):
    def hash(self, *, issuer: str, subject: str) -> str:
        return f"{issuer}:{subject}"


class FakeWithdrawnIdentityRegistry(WithdrawnIdentityRegistry):
    def __init__(self) -> None:
        self.marked_calls: list[list[str]] = []

    async def mark_withdrawn(self, *, identity_hashes: Sequence[str]) -> None:
        self.marked_calls.append(list(identity_hashes))

    async def exists(self, *, identity_hash: str) -> bool:
        return any(identity_hash in call for call in self.marked_calls)


@dataclass(frozen=True, slots=True)
class WithdrawUseCaseFixture:
    use_case: WithdrawAccountCommandUseCase
    repository: FakeCredentialRepository
    withdrawal_cleanup: NoOpWithdrawalCleanupCommandUseCase
    credit_cleaner: RecordingCreditWithdrawalCleaner
    push_token_cleaner: RecordingPushTokenWithdrawalCleaner
    withdrawn_identity_registry: FakeWithdrawnIdentityRegistry
    unit_of_work: FakeUnitOfWork
    event_publisher: RecordingEventPublisher


def _build_withdraw_use_case() -> WithdrawUseCaseFixture:
    repository = FakeCredentialRepository()
    withdrawal_cleanup = NoOpWithdrawalCleanupCommandUseCase()
    credit_cleaner = RecordingCreditWithdrawalCleaner()
    push_token_cleaner = RecordingPushTokenWithdrawalCleaner()
    withdrawn_identity_registry = FakeWithdrawnIdentityRegistry()
    unit_of_work = FakeUnitOfWork()
    event_publisher = RecordingEventPublisher()
    return WithdrawUseCaseFixture(
        use_case=WithdrawAccountCommandUseCase(
            credential_repository=repository,
            withdrawal_cleanup_command_use_case=withdrawal_cleanup,
            credit_withdrawal_cleaner=credit_cleaner,
            push_token_withdrawal_cleaner=push_token_cleaner,
            identity_hasher=FakeIdentityHasher(),
            withdrawn_identity_registry=withdrawn_identity_registry,
            unit_of_work=unit_of_work,
            event_publisher=event_publisher,
        ),
        repository=repository,
        withdrawal_cleanup=withdrawal_cleanup,
        credit_cleaner=credit_cleaner,
        push_token_cleaner=push_token_cleaner,
        withdrawn_identity_registry=withdrawn_identity_registry,
        unit_of_work=unit_of_work,
        event_publisher=event_publisher,
    )


async def test_withdraw_marks_all_linked_identities_before_deleting_auth_state() -> None:
    fixture = _build_withdraw_use_case()
    user_id = uuid4()
    credentials = UserCredential.create(user_id=user_id, credentials_id=uuid4(), role="user")
    google_identity = ExternalIdentity.create(
        issuer="google",
        subject="google-sub",
        provider="google",
        email="user@example.com",
        name="테스트 사용자",
        email_verified=True,
    )
    apple_identity = ExternalIdentity.create(
        issuer="apple",
        subject="apple-sub",
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

    assert len(fixture.withdrawn_identity_registry.marked_calls) == 1
    assert sorted(fixture.withdrawn_identity_registry.marked_calls[0]) == sorted(
        ["google:google-sub", "apple:apple-sub"]
    )
    # 삭제(delete_account_auth_state)는 tombstone 기록 이후에 일어난다.
    assert fixture.repository.credentials_by_identity == {}
    assert fixture.withdrawal_cleanup.executed_user_ids == [user_id]
    assert fixture.credit_cleaner.deleted_user_ids == [user_id]
    assert fixture.push_token_cleaner.deleted_user_ids == [user_id]
    assert fixture.unit_of_work.commit_count == 1
    assert len(fixture.event_publisher.published) == 1


async def test_withdraw_with_no_linked_identities_proceeds_without_marking_anything() -> None:
    fixture = _build_withdraw_use_case()
    user_id = uuid4()
    credentials_id = uuid4()

    await fixture.use_case.execute(
        WithdrawAccountCommand(user_id=user_id, credentials_id=credentials_id)
    )

    assert fixture.withdrawn_identity_registry.marked_calls == [[]]
    assert fixture.withdrawal_cleanup.executed_user_ids == [user_id]
    assert fixture.unit_of_work.commit_count == 1
