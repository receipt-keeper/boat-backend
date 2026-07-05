from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.modules.users.application.commands.provision.command import ProvisionUserCommand
from app.modules.users.application.commands.provision.result import ProvisionUserResult
from app.modules.users.application.ports.user_repository import UserRepository


class ProvisionUserCommandUseCase:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        unit_of_work: UnitOfWork,
        event_publisher: EventPublisher,
    ) -> None:
        self._user_repository = user_repository
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher

    async def execute(self, command: ProvisionUserCommand) -> ProvisionUserResult:
        user = await self._user_repository.create(name=command.name, email=command.email)
        await self._event_publisher.publish(user.pull_events())
        await self._unit_of_work.commit()
        return ProvisionUserResult(user_id=user.id)
