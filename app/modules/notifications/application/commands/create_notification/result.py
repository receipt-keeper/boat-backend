from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.notifications.domain.value_objects import (
    NotificationKind,
    NotificationTargetType,
)


@dataclass(frozen=True, slots=True)
class CreateNotificationResult:
    notification_id: UUID
    kind: NotificationKind
    message: str
    target_type: NotificationTargetType
    target_id: UUID | None
    created_at: datetime
    read_at: datetime | None
