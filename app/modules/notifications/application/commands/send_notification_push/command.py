from dataclasses import dataclass
from uuid import UUID

from app.modules.notifications.domain.value_objects import (
    NotificationKind,
    NotificationTargetType,
)


@dataclass(frozen=True, slots=True)
class SendNotificationPushCommand:
    user_id: UUID
    notification_id: UUID
    kind: NotificationKind
    message: str
    target_type: NotificationTargetType
    target_id: UUID | None
