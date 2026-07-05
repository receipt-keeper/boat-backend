from dataclasses import dataclass
from uuid import UUID

from app.core.domain.events import DomainEvent
from app.modules.notifications.domain.value_objects import NotificationMessageType


@dataclass(frozen=True, kw_only=True)
class NotificationCreated(DomainEvent):
    notification_id: UUID
    user_id: UUID
    message_type: NotificationMessageType
    kind: str
    title: str
    message: str
    resource_type: str | None
    resource_id: UUID | None
