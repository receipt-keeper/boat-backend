from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.push_cleanup import PushCleanup
from app.modules.auth.application.withdraw.schemas import WithdrawAccountCommand
from app.modules.users.application.delete.schemas import DeleteUserCommand
from app.modules.users.application.delete.use_case import DeleteUserUseCase


class WithdrawAccountUseCase:
    def __init__(
        self,
        *,
        credential_repository: CredentialRepository,
        delete_user_use_case: DeleteUserUseCase,
        push_cleanup: PushCleanup,
    ) -> None:
        self._credential_repository = credential_repository
        self._delete_user_use_case = delete_user_use_case
        self._push_cleanup = push_cleanup

    async def execute(self, command: WithdrawAccountCommand) -> None:
        await self._credential_repository.delete_account_auth_state(
            user_id=command.user_id,
            credentials_id=command.credentials_id,
        )
        await self._delete_user_use_case.execute(DeleteUserCommand(user_id=command.user_id))
        await self._push_cleanup.cleanup_withdrawn_account(
            user_id=command.user_id,
            credentials_id=command.credentials_id,
        )
