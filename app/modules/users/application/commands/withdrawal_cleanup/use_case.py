from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.modules.users.application.commands.withdrawal_cleanup.command import (
    WithdrawalCleanupCommand,
)
from app.modules.users.application.ports.user_repository import UserRepository
from app.modules.users.domain.events import UserWithdrawn


class WithdrawalCleanupCommandUseCase:
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

    async def execute(self, command: WithdrawalCleanupCommand) -> None:
        # 삭제 경로는 애그리거트를 로드하지 않고 user_id만으로 진행되므로(성능/락 최소화),
        # UserWithdrawn은 엔티티 팩토리가 아니라 이 use case에서 직접 기록한다.
        await self._user_repository.delete_account_state(user_id=command.user_id)
        await self._event_publisher.publish([UserWithdrawn(user_id=command.user_id)])
        await self._unit_of_work.commit()
