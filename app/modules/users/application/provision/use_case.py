from app.modules.users.application.ports.user_repository import UserRepository
from app.modules.users.application.provision.schemas import (
    ProvisionUserCommand,
    ProvisionUserResult,
)


class ProvisionUserUseCase:
    def __init__(self, *, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def execute(self, command: ProvisionUserCommand) -> ProvisionUserResult:
        user = await self._user_repository.create(name=command.name, email=command.email)
        return ProvisionUserResult(user_id=user.id)
