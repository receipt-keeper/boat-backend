from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GetNotificationSettingsQuery:
    user_id: UUID
