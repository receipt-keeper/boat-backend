from datetime import datetime
from uuid import UUID

from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.ports.notification_repository import (
    NotificationListCursor,
    NotificationListResult,
    NotificationRepository,
)
from app.modules.notifications.domain.model import NotificationSettings, UserNotification


class CreatedNotification:
    def __init__(self, *, command: CreateNotificationCommand) -> None:
        self.command = command


class NotificationRepositoryFake(NotificationRepository):
    def __init__(self, settings: dict[UUID, NotificationSettings]) -> None:
        self.settings = settings
        self.created: list[CreatedNotification] = []

    async def create(self, *, notification: UserNotification) -> UserNotification:
        self.created.append(
            CreatedNotification(
                command=CreateNotificationCommand(
                    user_id=notification.user_id,
                    message_type=notification.message_type,
                    kind=notification.kind.value,
                    title=notification.title.value,
                    message=notification.message.value,
                    resource_type=(
                        notification.resource_type.value if notification.resource_type else None
                    ),
                    resource_id=notification.resource_id,
                    metadata=dict(notification.metadata.value),
                )
            )
        )
        return notification

    async def list_by_user(
        self,
        *,
        user_id: UUID,
        cursor: NotificationListCursor | None,
        limit: int,
    ) -> NotificationListResult:
        raise NotImplementedError

    async def find_by_id_for_user(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
    ) -> UserNotification | None:
        raise NotImplementedError

    async def mark_read(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
        read_at: datetime,
    ) -> UserNotification | None:
        raise NotImplementedError

    async def get_settings(self, *, user_id: UUID) -> NotificationSettings:
        return self.settings.get(user_id, NotificationSettings.create(user_id=user_id))

    async def update_settings(
        self,
        *,
        user_id: UUID,
        push_enabled: bool | None,
        marketing_consent: bool | None,
    ) -> NotificationSettings:
        raise NotImplementedError
