from app.modules.notifications.domain.model import (
    NotificationSettings as DomainNotificationSettings,
)
from app.modules.notifications.domain.model import (
    UserNotification as DomainUserNotification,
)
from app.modules.notifications.domain.model import (
    UserPushToken as DomainUserPushToken,
)
from app.modules.notifications.domain.value_objects import (
    DevicePlatform,
    NotificationKind,
    NotificationTargetType,
)
from app.modules.notifications.infrastructure.persistence import orm


def notification_to_domain(record: orm.UserNotification) -> DomainUserNotification:
    return DomainUserNotification.create(
        notification_id=record.id,
        user_id=record.user_id,
        kind=NotificationKind(record.kind),
        message=record.message,
        target_type=NotificationTargetType(record.target_type),
        target_id=record.target_id,
        created_at=record.created_at,
        read_at=record.read_at,
    )


def notification_to_record(
    notification: DomainUserNotification,
) -> orm.UserNotification:
    return orm.UserNotification(
        id=notification.id,
        user_id=notification.user_id,
        kind=notification.kind.value,
        message=notification.message.value,
        target_type=notification.target_type.value,
        target_id=notification.target_id,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


def settings_to_domain(record: orm.NotificationSettings) -> DomainNotificationSettings:
    return DomainNotificationSettings.create(
        user_id=record.user_id,
        push_enabled=record.push_enabled,
        marketing_consent=record.marketing_consent,
    )


def settings_to_record(
    settings: DomainNotificationSettings,
) -> orm.NotificationSettings:
    return orm.NotificationSettings(
        user_id=settings.id,
        push_enabled=settings.push_enabled,
        marketing_consent=settings.marketing_consent,
    )


def push_token_to_domain(record: orm.UserPushToken) -> DomainUserPushToken:
    return DomainUserPushToken.create(
        push_token_id=record.id,
        user_id=record.user_id,
        device_id=record.device_id,
        fcm_token=record.fcm_token,
        platform=DevicePlatform(record.platform),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
