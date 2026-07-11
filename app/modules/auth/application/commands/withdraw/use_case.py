from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.credit_lifecycle import CreditWithdrawalCleaner
from app.modules.auth.application.ports.push_token_lifecycle import PushTokenWithdrawalCleaner
from app.modules.auth.application.ports.withdrawn_identity import (
    IdentityHasher,
    WithdrawnIdentityRegistry,
)
from app.modules.auth.domain.events import AccountWithdrawn
from app.modules.users.application.commands.withdrawal_cleanup.command import (
    WithdrawalCleanupCommand,
)
from app.modules.users.application.commands.withdrawal_cleanup.use_case import (
    WithdrawalCleanupCommandUseCase,
)


class WithdrawAccountCommandUseCase:
    def __init__(
        self,
        *,
        credential_repository: CredentialRepository,
        withdrawal_cleanup_command_use_case: WithdrawalCleanupCommandUseCase,
        credit_withdrawal_cleaner: CreditWithdrawalCleaner,
        push_token_withdrawal_cleaner: PushTokenWithdrawalCleaner,
        identity_hasher: IdentityHasher,
        withdrawn_identity_registry: WithdrawnIdentityRegistry,
        unit_of_work: UnitOfWork,
        event_publisher: EventPublisher,
    ) -> None:
        self._credential_repository = credential_repository
        self._withdrawal_cleanup_command_use_case = withdrawal_cleanup_command_use_case
        self._credit_withdrawal_cleaner = credit_withdrawal_cleaner
        self._push_token_withdrawal_cleaner = push_token_withdrawal_cleaner
        self._identity_hasher = identity_hasher
        self._withdrawn_identity_registry = withdrawn_identity_registry
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher

    async def execute(self, command: WithdrawAccountCommand) -> None:
        # 삭제 직전에 연결된 모든 external identity를 신원 해시로 tombstone 기록한다
        # (소셜 링크 후 다른 provider로 재가입하는 우회를 막기 위해 전부 기록).
        identities = await self._credential_repository.list_external_identities(
            credentials_id=command.credentials_id,
        )
        identity_hashes = [
            self._identity_hasher.hash(issuer=identity.issuer.value, subject=identity.subject.value)
            for identity in identities
        ]
        await self._withdrawn_identity_registry.mark_withdrawn(identity_hashes=identity_hashes)

        # 삭제 경로는 애그리거트를 로드하지 않고 user_id/credentials_id만으로 진행되므로
        # (성능/락 최소화), AccountWithdrawn은 엔티티 팩토리가 아니라 이 use case에서
        # 직접 기록한다 (users의 UserWithdrawn과 동일한 근거).
        await self._credential_repository.delete_account_auth_state(
            user_id=command.user_id,
            credentials_id=command.credentials_id,
        )
        await self._event_publisher.publish(
            [
                AccountWithdrawn(
                    credentials_id=command.credentials_id,
                    user_id=command.user_id,
                )
            ]
        )
        await self._withdrawal_cleanup_command_use_case.execute(
            WithdrawalCleanupCommand(user_id=command.user_id)
        )
        await self._credit_withdrawal_cleaner.delete_account_state(user_id=command.user_id)
        await self._push_token_withdrawal_cleaner.delete_account_state(user_id=command.user_id)
        await self._unit_of_work.commit()
