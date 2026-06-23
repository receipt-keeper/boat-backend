from app.core.application.unit_of_work import UnitOfWork
from app.modules.users.application.commands.delete.command import DeleteUserCommand
from app.modules.users.application.ports.user_repository import UserRepository


class DeleteUserCommandUseCase:
    def __init__(self, *, user_repository: UserRepository, unit_of_work: UnitOfWork) -> None:
        self._user_repository = user_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: DeleteUserCommand) -> None:
        await self._user_repository.delete_by_id(user_id=command.user_id)
        await self._unit_of_work.commit()
