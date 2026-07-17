from app.core.application.unit_of_work import UnitOfWork
from app.core.domain.exceptions import NotFoundError
from app.modules.notifications.application.commands.delete_notification.command import (
    DeleteNotificationCommand,
)
from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)


class DeleteNotificationCommandUseCase:
    def __init__(
        self,
        *,
        notification_repository: NotificationRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._notification_repository = notification_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: DeleteNotificationCommand) -> None:
        deleted = await self._notification_repository.delete_by_id_for_user(
            notification_id=command.notification_id,
            user_id=command.user_id,
        )
        if not deleted:
            raise NotFoundError("알림을 찾을 수 없습니다.")
        await self._unit_of_work.commit()
