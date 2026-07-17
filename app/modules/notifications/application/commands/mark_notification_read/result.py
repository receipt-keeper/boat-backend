from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.notifications.domain.value_objects import (
    NotificationCategory,
    NotificationMessageType,
)


@dataclass(frozen=True, slots=True)
class MarkNotificationReadResult:
    notification_id: UUID
    message_type: NotificationMessageType
    category: NotificationCategory
    kind: str
    title: str
    message: str
    resource_type: str | None
    resource_id: UUID | None
    metadata: dict[str, str]
    created_at: datetime
    read_at: datetime | None
