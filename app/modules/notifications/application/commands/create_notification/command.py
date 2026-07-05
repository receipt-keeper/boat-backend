from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from app.modules.notifications.domain.value_objects import NotificationMessageType


@dataclass(frozen=True, slots=True)
class CreateNotificationCommand:
    user_id: UUID
    message_type: NotificationMessageType
    kind: str
    title: str
    message: str
    resource_type: str | None = None
    resource_id: UUID | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)
