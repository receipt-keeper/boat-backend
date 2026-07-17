from datetime import date, time

from app.modules.notifications.domain.model import (
    NotificationSettings as DomainNotificationSettings,
)
from app.modules.notifications.domain.model import (
    UserNotification as DomainUserNotification,
)
from app.modules.notifications.domain.model import (
    UserPushToken as DomainUserPushToken,
)
from app.modules.notifications.domain.schedule_rule import (
    NotificationScheduleRule as DomainNotificationScheduleRule,
)
from app.modules.notifications.domain.value_objects import (
    DevicePlatform,
    NotificationCategory,
    NotificationMessageType,
)
from app.modules.notifications.infrastructure.persistence.orm import (
    NotificationSettings,
    UserNotification,
    UserPushToken,
)
from app.modules.notifications.infrastructure.persistence.schedule_rule_orm import (
    NotificationScheduleRule,
)


def schedule_rule_to_domain(
    record: NotificationScheduleRule,
) -> DomainNotificationScheduleRule:
    return DomainNotificationScheduleRule.create(
        campaign_key=record.campaign_key,
        enabled=record.enabled,
        target_kind=record.target_kind,
        day_offset=record.day_offset,
        first_delay_days=record.first_delay_days,
        repeat_interval_days=record.repeat_interval_days,
        lookback_days=record.lookback_days,
        send_time_local=record.send_time_local,
        requires_marketing_consent=record.requires_marketing_consent,
        title_template=record.title_template,
        body_template=record.body_template,
    )


def schedule_rule_to_insert_values(
    rule: DomainNotificationScheduleRule,
) -> dict[str, str | bool | date | time | int | None]:
    return {
        "campaign_key": rule.campaign_key,
        "enabled": rule.enabled,
        "target_kind": rule.target_kind.value,
        "day_offset": rule.day_offset,
        "first_delay_days": rule.first_delay_days,
        "repeat_interval_days": rule.repeat_interval_days,
        "lookback_days": rule.lookback_days,
        "send_time_local": rule.send_time_local,
        "requires_marketing_consent": rule.requires_marketing_consent,
        "title_template": rule.title_template,
        "body_template": rule.body_template,
    }


def notification_to_domain(record: UserNotification) -> DomainUserNotification:
    return DomainUserNotification.restore(
        notification_id=record.id,
        user_id=record.user_id,
        category=NotificationCategory(record.category),
        message_type=NotificationMessageType(record.message_type),
        kind=record.kind,
        title=record.title,
        message=record.message,
        resource_type=record.resource_type,
        resource_id=record.resource_id,
        metadata=dict(record.metadata_),
        created_at=record.created_at,
        read_at=record.read_at,
    )


def notification_to_record(
    notification: DomainUserNotification,
) -> UserNotification:
    return UserNotification(
        id=notification.id,
        user_id=notification.user_id,
        category=notification.category.value,
        message_type=notification.message_type.value,
        kind=notification.kind.value,
        title=notification.title.value,
        message=notification.message.value,
        resource_type=(
            notification.resource_type.value if notification.resource_type is not None else None
        ),
        resource_id=notification.resource_id,
        metadata_=dict(notification.metadata.value),
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


def settings_to_domain(record: NotificationSettings) -> DomainNotificationSettings:
    return DomainNotificationSettings.create(
        user_id=record.user_id,
        push_enabled=record.push_enabled,
        marketing_consent=record.marketing_consent,
    )


def settings_to_record(
    settings: DomainNotificationSettings,
) -> NotificationSettings:
    return NotificationSettings(
        user_id=settings.id,
        push_enabled=settings.push_enabled,
        marketing_consent=settings.marketing_consent,
    )


def push_token_to_domain(record: UserPushToken) -> DomainUserPushToken:
    return DomainUserPushToken.create(
        push_token_id=record.id,
        user_id=record.user_id,
        token=record.token,
        platform=DevicePlatform(record.platform),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
