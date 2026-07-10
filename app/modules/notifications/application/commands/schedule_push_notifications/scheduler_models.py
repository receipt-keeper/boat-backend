from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.schedule_push_notifications.result import (
    SchedulePushNotificationRuleSummary,
)
from app.modules.notifications.domain.schedule_occurrence import ScheduleOccurrenceKey
from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule


@dataclass(frozen=True, slots=True)
class DueScheduleRule:
    rule: NotificationScheduleRule
    target_date: date
    scheduled_for: datetime


@dataclass(frozen=True, slots=True)
class ScheduleCandidate:
    command: CreateNotificationCommand
    occurrence: ScheduleOccurrenceKey


@dataclass(frozen=True, slots=True)
class Accumulator:
    rule_summaries: tuple[SchedulePushNotificationRuleSummary, ...]
    candidates: int
    created: int
    skipped: int
    failed: int


type ScheduleAction = Literal["created", "skipped", "failed", "dry_run"]
