from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Final, assert_never
from zoneinfo import ZoneInfo

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.notifications.domain.schedule_rule import (
    NotificationScheduleRule,
    ScheduleRuleTargetKind,
)
from app.modules.notifications.domain.value_objects import NotificationMessageType

SYSTEM_TIMEZONE: Final = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class DueNotificationRule:
    rule: NotificationScheduleRule
    target_date: date


@dataclass(frozen=True, slots=True)
class NotificationDeliveryContract:
    message_type: NotificationMessageType
    kind: str
    resource_type: str | None


def resolve_due_notification_rule(
    *,
    rule: NotificationScheduleRule,
    now: datetime,
    target_date: date | None,
) -> DueNotificationRule | None:
    _validate_aware_now(now)
    if not rule.enabled:
        return None

    local_now = now.astimezone(SYSTEM_TIMEZONE)
    current_date = local_now.date()
    resolved_target_date = target_date or current_date
    if resolved_target_date > current_date:
        return None
    if (
        resolved_target_date == current_date
        and local_now.replace(tzinfo=None).time() < rule.send_time_local
    ):
        return None
    return DueNotificationRule(rule=rule, target_date=resolved_target_date)


def delivery_contract_for(target_kind: ScheduleRuleTargetKind) -> NotificationDeliveryContract:
    match target_kind:
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
            return NotificationDeliveryContract(
                message_type=NotificationMessageType.TRANSACTIONAL,
                kind="warranty_expiry",
                resource_type="receipt",
            )
        case ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT:
            return NotificationDeliveryContract(
                message_type=NotificationMessageType.MARKETING,
                kind="receipt_registration_reminder",
                resource_type=None,
            )
        case ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT:
            return NotificationDeliveryContract(
                message_type=NotificationMessageType.MARKETING,
                kind="receipt_inactivity_reminder",
                resource_type=None,
            )
        case ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER:
            return NotificationDeliveryContract(
                message_type=NotificationMessageType.MARKETING,
                kind="receipt_analysis_reminder",
                resource_type=None,
            )
        case unreachable:
            assert_never(unreachable)


def matches_join_cadence(
    *,
    rule: NotificationScheduleRule,
    days_since_joined: int,
) -> bool:
    first_due_day = _first_due_day(rule)
    if days_since_joined < first_due_day:
        return False

    interval = rule.repeat_interval_days
    if interval is None or interval == 0:
        return days_since_joined == first_due_day
    return (days_since_joined - first_due_day) % interval == 0


def registration_age_days_on(*, target_date: date, registered_at: datetime) -> int:
    return (target_date - registered_at.astimezone(SYSTEM_TIMEZONE).date()).days


def matches_receipt_activity(
    *,
    target_kind: ScheduleRuleTargetKind,
    receipt_count: int,
) -> bool:
    match target_kind:
        case ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT:
            return receipt_count == 0
        case ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT:
            return receipt_count > 0
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT | ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER:
            return False
        case unreachable:
            assert_never(unreachable)


def receipt_activity_since_for(due_rule: DueNotificationRule) -> datetime | None:
    match due_rule.rule.target_kind:
        case ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT:
            return None
        case ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT:
            lookback_days = due_rule.rule.lookback_days
            if lookback_days is None:
                raise RuntimeError("비활성 영수증 유도 예약 규칙에 lookbackDays가 필요합니다.")
            return datetime.combine(
                due_rule.target_date,
                time.min,
                tzinfo=SYSTEM_TIMEZONE,
            ) - timedelta(days=lookback_days)
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT | ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER:
            raise RuntimeError("영수증 활동 조회 대상이 아닌 예약 규칙입니다.")
        case unreachable:
            assert_never(unreachable)


def render_notification_text(template: str, *, item_name: str) -> str:
    return template.replace("[기기명]", item_name)


def _validate_aware_now(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValidationError(
            [ErrorDetail(field="now", message="예약 알림 기준 시각이 올바르지 않습니다.")]
        )


def _first_due_day(rule: NotificationScheduleRule) -> int:
    if rule.first_delay_days is not None:
        return rule.first_delay_days
    if rule.lookback_days is not None:
        return rule.lookback_days
    return 0
