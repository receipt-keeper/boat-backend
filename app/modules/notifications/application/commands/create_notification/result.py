from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.notifications.domain.value_objects import NotificationMessageType


@dataclass(frozen=True, slots=True)
class CreateNotificationResult:
    notification_id: UUID
    message_type: NotificationMessageType
    kind: str
    title: str
    message: str
    resource_type: str | None
    resource_id: UUID | None
    metadata: dict[str, str]
    created_at: datetime
    read_at: datetime | None


@dataclass(frozen=True, slots=True)
class SkippedMarketingConsent:
    pass


type NotificationCreationResult = CreateNotificationResult | SkippedMarketingConsent
