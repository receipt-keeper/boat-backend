from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from app.modules.notifications.application.commands.schedule_push_notifications.command import (
    SchedulePushNotificationsCommand,
)
from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule

from .scheduler_models import DueScheduleRule

SYSTEM_TIMEZONE: Final = ZoneInfo("Asia/Seoul")


def due_schedule_rule(
    *,
    rule: NotificationScheduleRule,
    command: SchedulePushNotificationsCommand,
) -> DueScheduleRule | None:
    if not rule.enabled:
        return None
    local_now = command.now.astimezone(SYSTEM_TIMEZONE)
    current_date = local_now.date()
    target_date = command.target_date or current_date
    if target_date > current_date:
        return None
    if target_date == current_date and local_now.replace(tzinfo=None).time() < rule.send_time_local:
        return None
    return DueScheduleRule(
        rule=rule,
        target_date=target_date,
        scheduled_for=datetime.combine(target_date, rule.send_time_local, tzinfo=SYSTEM_TIMEZONE),
    )
