from collections.abc import Callable
from datetime import UTC, datetime

from app.core.application.event_publisher import EventPublisher
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


def _result_from_notification(notification: UserNotification) -> CreateNotificationResult:
    return CreateNotificationResult(
        notification_id=notification.id,
        message_type=notification.message_type,
        kind=notification.kind.value,
        title=notification.title.value,
        message=notification.message.value,
        resource_type=(notification.resource_type.value if notification.resource_type else None),
        resource_id=notification.resource_id,
        metadata=dict(notification.metadata.value),
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


class NotificationCreator:
    def __init__(
        self,
        *,
        notification_repository: NotificationRepository,
        event_publisher: EventPublisher,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._notification_repository = notification_repository
        self._event_publisher = event_publisher
        self._clock = clock

    async def create(self, command: CreateNotificationCommand) -> CreateNotificationResult:
        notification = UserNotification.create(
            user_id=command.user_id,
            message_type=command.message_type,
            kind=command.kind,
            title=command.title,
            message=command.message,
            resource_type=command.resource_type,
            resource_id=command.resource_id,
            metadata=command.metadata,
            created_at=self._clock(),
        )
        saved = await self._notification_repository.create(notification=notification)
        events = saved.pull_events()
        await self._event_publisher.publish(events)
        return _result_from_notification(saved)


class CreateNotificationCommandUseCase:
    def __init__(
        self,
        *,
        notification_repository: NotificationRepository,
        unit_of_work: UnitOfWork,
        event_publisher: EventPublisher,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._creator = NotificationCreator(
            notification_repository=notification_repository,
            event_publisher=event_publisher,
            clock=clock,
        )

    async def execute(self, command: CreateNotificationCommand) -> CreateNotificationResult:
        result = await self._creator.create(command)
        await self._unit_of_work.commit()
        return result
