from dataclasses import dataclass
from uuid import UUID

from app.modules.notifications.domain.value_objects import (
    NotificationKind,
    NotificationTargetType,
)


@dataclass(frozen=True, slots=True)
class CreateNotificationCommand:
    user_id: UUID
    kind: NotificationKind
    message: str
    target_type: NotificationTargetType = NotificationTargetType.NONE
    target_id: UUID | None = None
