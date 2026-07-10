from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from app.modules.notifications.application.commands.schedule_push_notifications.command import (
    SchedulePushNotificationsCommand,
)
from app.modules.notifications.domain.model import NotificationSettings
from app.modules.notifications.domain.schedule_rule import (
    NotificationScheduleRule,
    ScheduleRuleTargetKind,
)
from app.modules.receipts.application.ports.receipt_repository import (
    ReceiptRegistrationActivityCandidate,
    WarrantyNotificationCandidate,
)
from app.modules.users.application.ports.user_repository import UserNotificationCandidate

NOW = datetime(2026, 7, 9, 9, 0, tzinfo=UTC)
TARGET_DATE = date(2026, 7, 9)
USER_ID = UUID("00000000-0000-0000-0000-000000000101")
CONSENT_USER_ID = UUID("00000000-0000-0000-0000-000000000102")
NO_CONSENT_USER_ID = UUID("00000000-0000-0000-0000-000000000103")
FOURTEEN_DAY_USER_ID = UUID("00000000-0000-0000-0000-000000000104")
RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000201")
OTHER_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000202")


def schedule_command(
    *,
    target_date: date | None = TARGET_DATE,
    now: datetime = NOW,
    dry_run: bool = False,
) -> SchedulePushNotificationsCommand:
    return SchedulePushNotificationsCommand(
        target_date=target_date,
        now=now,
        campaign_key=None,
        dry_run=dry_run,
        batch_size=10,
    )


def warranty_rule(
    *,
    campaign_key: str,
    day_offset: int,
    enabled: bool = True,
    send_time_local: time = time(9, 0),
    body_template: str = "[기기명] 무상 AS 7일 남았어요.",
) -> NotificationScheduleRule:
    return NotificationScheduleRule.create(
        campaign_key=campaign_key,
        enabled=enabled,
        target_kind=ScheduleRuleTargetKind.WARRANTY_RECEIPT.value,
        day_offset=day_offset,
        first_delay_days=None,
        repeat_interval_days=None,
        lookback_days=None,
        send_time_local=send_time_local,
        requires_marketing_consent=False,
        title_template=campaign_key,
        body_template=body_template,
    )


def engagement_rule(
    *,
    campaign_key: str,
    target_kind: ScheduleRuleTargetKind,
    first_delay_days: int | None,
    repeat_interval_days: int | None,
    lookback_days: int | None = 7,
    send_time_local: time = time(9, 0),
) -> NotificationScheduleRule:
    return NotificationScheduleRule.create(
        campaign_key=campaign_key,
        enabled=True,
        target_kind=target_kind.value,
        day_offset=None,
        first_delay_days=first_delay_days,
        repeat_interval_days=repeat_interval_days,
        lookback_days=lookback_days,
        send_time_local=send_time_local,
        requires_marketing_consent=True,
        title_template=campaign_key,
        body_template="영수증을 등록하고 보증 기간을 챙기세요.",
    )


def warranty_candidate(
    *,
    receipt_id: UUID = RECEIPT_ID,
    expires_on: date = date(2026, 7, 16),
    days_until_expiry: int = 7,
    item_name: str = "공기청정기",
) -> WarrantyNotificationCandidate:
    return WarrantyNotificationCandidate(
        user_id=USER_ID,
        receipt_id=receipt_id,
        item_name=item_name,
        expires_on=expires_on,
        days_until_expiry=days_until_expiry,
    )


def user_candidate(
    *,
    user_id: UUID,
    days_since_joined: int,
) -> UserNotificationCandidate:
    created_at = NOW - timedelta(days=days_since_joined)
    return UserNotificationCandidate(
        user_id=user_id,
        created_at=created_at,
        days_since_joined=days_since_joined,
        cursor_created_at=created_at,
        cursor_id=user_id,
    )


def activity_candidate(
    *,
    user_id: UUID,
    receipt_count: int = 0,
    last_receipt_created_at: datetime | None = None,
) -> ReceiptRegistrationActivityCandidate:
    return ReceiptRegistrationActivityCandidate(
        user_id=user_id,
        last_receipt_created_at=last_receipt_created_at,
        receipt_count=receipt_count,
        cursor_user_id=user_id,
    )


def consent_settings(*user_ids: UUID) -> dict[UUID, NotificationSettings]:
    return {
        user_id: NotificationSettings.create(user_id=user_id, marketing_consent=True)
        for user_id in user_ids
    }
