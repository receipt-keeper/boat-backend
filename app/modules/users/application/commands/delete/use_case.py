from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.modules.users.application.commands.delete.command import DeleteUserCommand
from app.modules.users.application.ports.user_repository import UserRepository
from app.modules.users.domain.events import UserWithdrawn


class DeleteUserCommandUseCase:
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

    async def execute(self, command: DeleteUserCommand) -> None:
        # withdrawal_cleanup과 동일한 이유로 use case에서 직접 기록한다(엔티티 미로드).
        await self._user_repository.delete_by_id(user_id=command.user_id)
        await self._event_publisher.publish([UserWithdrawn(user_id=command.user_id)])
        await self._unit_of_work.commit()
