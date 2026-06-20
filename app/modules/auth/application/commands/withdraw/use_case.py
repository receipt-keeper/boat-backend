from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.application.ports.credential_repository import CredentialRepository
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
    ) -> None:
        self._credential_repository = credential_repository
        self._withdrawal_cleanup_command_use_case = withdrawal_cleanup_command_use_case

    async def execute(self, command: WithdrawAccountCommand) -> None:
        await self._credential_repository.delete_account_auth_state(
            user_id=command.user_id,
            credentials_id=command.credentials_id,
        )
        await self._withdrawal_cleanup_command_use_case.execute(
            WithdrawalCleanupCommand(user_id=command.user_id)
        )
