from dataclasses import dataclass
from uuid import UUID

from app.modules.notifications.domain.value_objects import (
    NotificationCategory,
    NotificationMessageType,
)


@dataclass(frozen=True, slots=True)
class SendNotificationPushCommand:
    user_id: UUID
    notification_id: UUID
    message_type: NotificationMessageType
    kind: str
    title: str
    message: str
    resource_type: str | None
    resource_id: UUID | None
    category: NotificationCategory = NotificationCategory.PRODUCT_MANAGEMENT
