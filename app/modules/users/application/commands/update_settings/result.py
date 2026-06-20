from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UpdateSettingsResult:
    user_id: UUID
    notification_enabled: bool
    marketing_consent: bool
