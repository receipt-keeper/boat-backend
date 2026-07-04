from dataclasses import dataclass
from uuid import UUID

from app.modules.notifications.domain.value_objects import NotificationCategory


@dataclass(frozen=True, slots=True)
class CreateNotificationCommand:
    user_id: UUID
    category: NotificationCategory
    kind: str
    title: str
    message: str
    resource_type: str | None = None
    resource_id: UUID | None = None
