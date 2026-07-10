from datetime import date
from typing import assert_never

from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.domain.schedule_occurrence import (
    ScheduleOccurrenceKey,
    target_type_for_kind,
)
from app.modules.notifications.domain.schedule_rule import (
    NotificationScheduleRule,
    ScheduleRuleTargetKind,
)
from app.modules.notifications.domain.value_objects import NotificationMessageType
from app.modules.receipts.application.ports.receipt_repository import (
    ReceiptRegistrationActivityCandidate,
    WarrantyNotificationCandidate,
)
from app.modules.users.application.ports.user_repository import UserNotificationCandidate

from .scheduler_models import ScheduleCandidate


def warranty_schedule_candidate(
    *,
    rule: NotificationScheduleRule,
    candidate: WarrantyNotificationCandidate,
    occurrence_on: date,
) -> ScheduleCandidate:
    return ScheduleCandidate(
        command=CreateNotificationCommand(
            user_id=candidate.user_id,
            message_type=_message_type(rule.target_kind),
            kind=_kind(rule.target_kind),
            title=_render(rule.title_template, item_name=candidate.item_name),
            message=_render(rule.body_template, item_name=candidate.item_name),
            resource_type=_resource_type(rule.target_kind),
            resource_id=candidate.receipt_id,
            metadata={
                "daysUntilExpiry": str(candidate.days_until_expiry),
            },
        ),
        occurrence=ScheduleOccurrenceKey(
            campaign_key=rule.campaign_key,
            target_type=target_type_for_kind(rule.target_kind),
            target_id=candidate.receipt_id,
            occurrence_on=occurrence_on,
        ),
    )


def engagement_schedule_candidate(
    *,
    rule: NotificationScheduleRule,
    candidate: UserNotificationCandidate,
    bucket_on: date,
) -> ScheduleCandidate:
    return ScheduleCandidate(
        command=CreateNotificationCommand(
            user_id=candidate.user_id,
            message_type=_message_type(rule.target_kind),
            kind=_kind(rule.target_kind),
            title=rule.title_template,
            message=rule.body_template,
            resource_type=None,
            resource_id=None,
            metadata={},
        ),
        occurrence=ScheduleOccurrenceKey(
            campaign_key=rule.campaign_key,
            target_type=target_type_for_kind(rule.target_kind),
            target_id=candidate.user_id,
            occurrence_on=bucket_on,
        ),
    )


def activity_schedule_candidate(
    *,
    rule: NotificationScheduleRule,
    user_candidate: UserNotificationCandidate,
    activity_candidate: ReceiptRegistrationActivityCandidate,
    bucket_on: date,
) -> ScheduleCandidate:
    scheduled = engagement_schedule_candidate(
        rule=rule,
        candidate=user_candidate,
        bucket_on=bucket_on,
    )
    return ScheduleCandidate(
        command=CreateNotificationCommand(
            user_id=scheduled.command.user_id,
            message_type=scheduled.command.message_type,
            kind=scheduled.command.kind,
            title=scheduled.command.title,
            message=scheduled.command.message,
            resource_type=None,
            resource_id=None,
            metadata={
                **dict(scheduled.command.metadata),
                "receiptCount": str(activity_candidate.receipt_count),
            },
        ),
        occurrence=scheduled.occurrence,
    )


def matches_join_rule(
    *,
    rule: NotificationScheduleRule,
    candidate: UserNotificationCandidate,
) -> bool:
    delay = _rule_delay_days(rule)
    if candidate.days_since_joined < delay:
        return False
    interval = rule.repeat_interval_days
    if interval is None or interval == 0:
        return candidate.days_since_joined == delay
    return (candidate.days_since_joined - delay) % interval == 0


def _rule_delay_days(rule: NotificationScheduleRule) -> int:
    if rule.first_delay_days is not None:
        return rule.first_delay_days
    if rule.lookback_days is not None:
        return rule.lookback_days
    return 0


def _resource_type(target_kind: ScheduleRuleTargetKind) -> str | None:
    match target_kind:
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
            return "receipt"
        case (
            ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT
            | ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT
            | ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER
        ):
            return None
        case unreachable:
            assert_never(unreachable)


def _message_type(target_kind: ScheduleRuleTargetKind) -> NotificationMessageType:
    match target_kind:
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
            return NotificationMessageType.TRANSACTIONAL
        case (
            ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT
            | ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT
            | ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER
        ):
            return NotificationMessageType.MARKETING
        case unreachable:
            assert_never(unreachable)


def _kind(target_kind: ScheduleRuleTargetKind) -> str:
    match target_kind:
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
            return "warranty"
        case ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT:
            return "engagement_unregistered_receipt"
        case ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT:
            return "engagement_inactive_receipt"
        case ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER:
            return "engagement_all_user"
        case unreachable:
            assert_never(unreachable)


def _render(template: str, *, item_name: str) -> str:
    return template.replace("[기기명]", item_name)
