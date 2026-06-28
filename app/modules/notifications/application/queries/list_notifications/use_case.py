from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)
from app.modules.notifications.application.queries.list_notifications.query import (
    ListNotificationsQuery,
)
from app.modules.notifications.application.queries.list_notifications.result import (
    ListNotificationsResult,
    NotificationListItemResult,
)


class ListNotificationsQueryUseCase:
    def __init__(self, *, notification_repository: NotificationRepository) -> None:
        self._notification_repository = notification_repository

    async def execute(self, query: ListNotificationsQuery) -> ListNotificationsResult:
        offset = _cursor_offset(query.cursor)
        result = await self._notification_repository.list_by_user(
            user_id=query.user_id,
            offset=offset,
            limit=query.limit,
        )
        end = offset + len(result.notifications)
        has_next = end < result.total_count
        return ListNotificationsResult(
            notifications=tuple(
                NotificationListItemResult(
                    notification_id=notification.id,
                    kind=notification.kind,
                    message=notification.message.value,
                    target_type=notification.target_type,
                    target_id=notification.target_id,
                    created_at=notification.created_at,
                    read_at=notification.read_at,
                )
                for notification in result.notifications
            ),
            next_cursor=str(end) if has_next else None,
            has_next=has_next,
            limit=query.limit,
            total_count=result.total_count,
        )


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None or not cursor.isdecimal():
        return 0
    return int(cursor)
