from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from app.core.domain.exceptions import DomainError
from app.modules.notifications.application.ports.notification_repository import (
    NotificationListCursor,
    NotificationRepository,
)
from app.modules.notifications.application.queries.list_notifications.query import (
    ListNotificationsQuery,
)
from app.modules.notifications.application.queries.list_notifications.result import (
    ListNotificationsResult,
    NotificationListItemResult,
)

_CURSOR_SEPARATOR: Final = "|"


class InvalidNotificationCursorError(DomainError):
    def __init__(self) -> None:
        super().__init__("알림 목록 cursor가 올바르지 않습니다.")


class ListNotificationsQueryUseCase:
    def __init__(self, *, notification_repository: NotificationRepository) -> None:
        self._notification_repository = notification_repository

    async def execute(self, query: ListNotificationsQuery) -> ListNotificationsResult:
        cursor = _parse_cursor(query.cursor)
        result = await self._notification_repository.list_by_user(
            user_id=query.user_id,
            cursor=cursor,
            limit=query.limit,
        )
        notifications = tuple(
            NotificationListItemResult(
                notification_id=notification.id,
                category=notification.category,
                kind=notification.kind.value,
                title=notification.title.value,
                message=notification.message.value,
                resource_type=(
                    notification.resource_type.value if notification.resource_type else None
                ),
                resource_id=notification.resource_id,
                metadata=dict(notification.metadata.value),
                created_at=notification.created_at,
                read_at=notification.read_at,
            )
            for notification in result.notifications
        )
        return ListNotificationsResult(
            notifications=notifications,
            next_cursor=_next_cursor(notifications) if result.has_next else None,
            has_next=result.has_next,
            limit=query.limit,
            total_count=result.total_count,
        )


def _parse_cursor(cursor: str | None) -> NotificationListCursor | None:
    if cursor is None:
        return None

    parts = cursor.split(_CURSOR_SEPARATOR)
    if len(parts) != 2:
        raise InvalidNotificationCursorError()

    try:
        created_at = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
        notification_id = UUID(parts[1])
    except ValueError as exc:
        raise InvalidNotificationCursorError from exc

    if created_at.tzinfo is None:
        raise InvalidNotificationCursorError()

    return NotificationListCursor(created_at=created_at, notification_id=notification_id)


def _next_cursor(notifications: tuple[NotificationListItemResult, ...]) -> str | None:
    if not notifications:
        return None

    last_notification = notifications[-1]
    created_at = last_notification.created_at.astimezone(UTC)
    created_at_text = created_at.isoformat().replace("+00:00", "Z")
    return f"{created_at_text}{_CURSOR_SEPARATOR}{last_notification.notification_id}"
