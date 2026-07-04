from collections.abc import Callable
from datetime import UTC, datetime

from app.core.application.unit_of_work import UnitOfWork
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.result import (
    CreateNotificationResult,
)
from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)
from app.modules.notifications.domain.model import UserNotification


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CreateNotificationCommandUseCase:
    def __init__(
        self,
        *,
        notification_repository: NotificationRepository,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._notification_repository = notification_repository
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def execute(self, command: CreateNotificationCommand) -> CreateNotificationResult:
        notification = UserNotification.create(
            user_id=command.user_id,
            category=command.category,
            kind=command.kind,
            title=command.title,
            message=command.message,
            resource_type=command.resource_type,
            resource_id=command.resource_id,
            created_at=self._clock(),
        )
        saved = await self._notification_repository.create(notification=notification)
        await self._unit_of_work.commit()
        return CreateNotificationResult(
            notification_id=saved.id,
            category=saved.category,
            kind=saved.kind.value,
            title=saved.title.value,
            message=saved.message.value,
            resource_type=saved.resource_type.value if saved.resource_type else None,
            resource_id=saved.resource_id,
            created_at=saved.created_at,
            read_at=saved.read_at,
        )
