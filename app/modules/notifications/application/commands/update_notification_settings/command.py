from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UpdateNotificationSettingsCommand:
    user_id: UUID
    push_enabled: bool | None = None
    marketing_consent: bool | None = None
