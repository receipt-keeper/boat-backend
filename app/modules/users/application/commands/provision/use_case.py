from app.core.application.unit_of_work import UnitOfWork
from app.modules.users.application.commands.provision.command import ProvisionUserCommand
from app.modules.users.application.commands.provision.result import ProvisionUserResult
from app.modules.users.application.ports.user_repository import UserRepository


class ProvisionUserCommandUseCase:
    def __init__(self, *, user_repository: UserRepository, unit_of_work: UnitOfWork) -> None:
        self._user_repository = user_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: ProvisionUserCommand) -> ProvisionUserResult:
        user = await self._user_repository.create(name=command.name, email=command.email)
        await self._unit_of_work.commit()
        return ProvisionUserResult(user_id=user.id)
