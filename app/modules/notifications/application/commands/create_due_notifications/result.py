from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateDueNotificationRuleSummary:
    campaign_key: str
    candidates: int
    created: int
    skipped: int
    failed: int


@dataclass(frozen=True, slots=True)
class CreateDueNotificationsResult:
    rules: tuple[CreateDueNotificationRuleSummary, ...]
    candidates: int
    created: int
    skipped: int
    failed: int
    dry_run: bool
