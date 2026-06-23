from app.core.application.unit_of_work import UnitOfWork
from app.modules.users.application.commands.delete_push_token.command import DeletePushTokenCommand
from app.modules.users.application.ports.user_repository import UserRepository


class DeletePushTokenCommandUseCase:
    def __init__(self, *, user_repository: UserRepository, unit_of_work: UnitOfWork) -> None:
        self._user_repository = user_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: DeletePushTokenCommand) -> None:
        await self._user_repository.delete_push_token(
            user_id=command.user_id,
            device_id=command.device_id,
        )
        await self._unit_of_work.commit()
