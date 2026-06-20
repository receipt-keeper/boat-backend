from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UpdateSettingsCommand:
    user_id: UUID
    notification_enabled: bool | None = None
    marketing_consent: bool | None = None
