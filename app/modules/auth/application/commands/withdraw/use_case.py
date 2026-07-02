from app.core.application.unit_of_work import UnitOfWork
from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.credit_lifecycle import CreditWithdrawalCleaner
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
        unit_of_work: UnitOfWork,
    ) -> None:
        self._credential_repository = credential_repository
        self._withdrawal_cleanup_command_use_case = withdrawal_cleanup_command_use_case
        self._credit_withdrawal_cleaner = credit_withdrawal_cleaner
        self._unit_of_work = unit_of_work

    async def execute(self, command: WithdrawAccountCommand) -> None:
        await self._credential_repository.delete_account_auth_state(
            user_id=command.user_id,
            credentials_id=command.credentials_id,
        )
        await self._withdrawal_cleanup_command_use_case.execute(
            WithdrawalCleanupCommand(user_id=command.user_id)
        )
        await self._credit_withdrawal_cleaner.delete_account_state(user_id=command.user_id)
        await self._unit_of_work.commit()
