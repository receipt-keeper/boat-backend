from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.push_cleanup import PushCleanup
from app.modules.users.application.commands.delete.command import DeleteUserCommand
from app.modules.users.application.commands.delete.use_case import DeleteUserCommandUseCase


class WithdrawAccountCommandUseCase:
    def __init__(
        self,
        *,
        credential_repository: CredentialRepository,
        delete_user_command_use_case: DeleteUserCommandUseCase,
        push_cleanup: PushCleanup,
    ) -> None:
        self._credential_repository = credential_repository
        self._delete_user_command_use_case = delete_user_command_use_case
        self._push_cleanup = push_cleanup

    async def execute(self, command: WithdrawAccountCommand) -> None:
        await self._credential_repository.delete_account_auth_state(
            user_id=command.user_id,
            credentials_id=command.credentials_id,
        )
        await self._delete_user_command_use_case.execute(DeleteUserCommand(user_id=command.user_id))
        await self._push_cleanup.cleanup_withdrawn_account(
            user_id=command.user_id,
            credentials_id=command.credentials_id,
        )
