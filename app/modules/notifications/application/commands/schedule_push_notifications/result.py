from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SchedulePushNotificationRuleSummary:
    campaign_key: str
    candidates: int
    created: int
    skipped: int
    failed: int


@dataclass(frozen=True, slots=True)
class SchedulePushNotificationsResult:
    rules: tuple[SchedulePushNotificationRuleSummary, ...]
    candidates: int
    created: int
    skipped: int
    failed: int
    dry_run: bool
