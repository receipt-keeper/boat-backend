from collections.abc import Callable
from datetime import UTC, datetime

from app.core.application.unit_of_work import UnitOfWork
from app.core.domain.exceptions import NotFoundError
from app.modules.notifications.application.commands.mark_notification_read.command import (
    MarkNotificationReadCommand,
)
from app.modules.notifications.application.commands.mark_notification_read.result import (
    MarkNotificationReadResult,
)
from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MarkNotificationReadCommandUseCase:
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

    async def execute(self, command: MarkNotificationReadCommand) -> MarkNotificationReadResult:
        # 동의 철회와 읽음 처리의 가시성을 원자적으로 맞추기 위해 설정 행을 잠근다.
        await self._notification_repository.get_settings_for_update(user_id=command.user_id)
        notification = await self._notification_repository.mark_read(
            user_id=command.user_id,
            notification_id=command.notification_id,
            read_at=self._clock(),
        )
        if notification is None:
            raise NotFoundError("알림을 찾을 수 없습니다.")
        await self._unit_of_work.commit()
        return MarkNotificationReadResult(
            notification_id=notification.id,
            message_type=notification.message_type,
            kind=notification.kind.value,
            title=notification.title.value,
            message=notification.message.value,
            resource_type=notification.resource_type.value if notification.resource_type else None,
            resource_id=notification.resource_id,
            metadata=dict(notification.metadata.value),
            created_at=notification.created_at,
            read_at=notification.read_at,
        )
