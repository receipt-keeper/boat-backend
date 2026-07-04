from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.notifications.domain.value_objects import NotificationCategory


@dataclass(frozen=True, slots=True)
class NotificationListItemResult:
    notification_id: UUID
    category: NotificationCategory
    kind: str
    title: str
    message: str
    resource_type: str | None
    resource_id: UUID | None
    created_at: datetime
    read_at: datetime | None


@dataclass(frozen=True, slots=True)
class ListNotificationsResult:
    notifications: tuple[NotificationListItemResult, ...]
    next_cursor: str | None
    has_next: bool
    limit: int
    total_count: int
