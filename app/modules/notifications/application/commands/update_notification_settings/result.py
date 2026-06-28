from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UpdateNotificationSettingsResult:
    push_enabled: bool
    marketing_consent: bool
