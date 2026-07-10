from dataclasses import dataclass
from uuid import UUID

from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.domain.due_notification import (
    DueNotificationRule,
    delivery_contract_for,
    render_notification_text,
)
from app.modules.notifications.domain.schedule_occurrence import (
    ScheduleOccurrenceKey,
    target_type_for_kind,
)
from app.modules.notifications.domain.value_objects import NotificationMessage, NotificationTitle


@dataclass(frozen=True, slots=True)
class DueNotification:
    command: CreateNotificationCommand
    occurrence: ScheduleOccurrenceKey


def warranty_expiry_notification(
    *,
    due_rule: DueNotificationRule,
    user_id: UUID,
    receipt_id: UUID,
    item_name: str,
    days_until_expiry: int,
) -> DueNotification:
    delivery = delivery_contract_for(due_rule.rule.target_kind)
    return DueNotification(
        command=CreateNotificationCommand(
            user_id=user_id,
            message_type=delivery.message_type,
            kind=delivery.kind,
            title=render_notification_text(
                due_rule.rule.title_template,
                item_name=item_name,
                max_length=NotificationTitle.MAX_LENGTH,
            ),
            message=render_notification_text(
                due_rule.rule.body_template,
                item_name=item_name,
                max_length=NotificationMessage.MAX_LENGTH,
            ),
            resource_type=delivery.resource_type,
            resource_id=receipt_id,
            metadata={"daysUntilExpiry": str(days_until_expiry)},
        ),
        occurrence=ScheduleOccurrenceKey(
            campaign_key=due_rule.rule.campaign_key,
            target_type=target_type_for_kind(due_rule.rule.target_kind),
            target_id=receipt_id,
            occurrence_on=due_rule.target_date,
        ),
    )


def receipt_reminder_notification(
    *,
    due_rule: DueNotificationRule,
    user_id: UUID,
    receipt_count: int | None = None,
) -> DueNotification:
    delivery = delivery_contract_for(due_rule.rule.target_kind)
    metadata = {} if receipt_count is None else {"receiptCount": str(receipt_count)}
    return DueNotification(
        command=CreateNotificationCommand(
            user_id=user_id,
            message_type=delivery.message_type,
            kind=delivery.kind,
            title=due_rule.rule.title_template,
            message=due_rule.rule.body_template,
            resource_type=delivery.resource_type,
            resource_id=None,
            metadata=metadata,
        ),
        occurrence=ScheduleOccurrenceKey(
            campaign_key=due_rule.rule.campaign_key,
            target_type=target_type_for_kind(due_rule.rule.target_kind),
            target_id=user_id,
            occurrence_on=due_rule.target_date,
        ),
    )
