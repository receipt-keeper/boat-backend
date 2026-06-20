from app.modules.users.application.commands.delete_push_token.command import DeletePushTokenCommand
from app.modules.users.application.ports.user_repository import UserRepository


class DeletePushTokenCommandUseCase:
    def __init__(self, *, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def execute(self, command: DeletePushTokenCommand) -> None:
        await self._user_repository.delete_push_token(
            user_id=command.user_id,
            device_id=command.device_id,
        )
