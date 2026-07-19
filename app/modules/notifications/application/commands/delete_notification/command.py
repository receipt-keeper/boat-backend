from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DeleteNotificationCommand:
    user_id: UUID
    notification_id: UUID
