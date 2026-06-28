from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetNotificationSettingsResult:
    push_enabled: bool
    marketing_consent: bool
