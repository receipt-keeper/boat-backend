from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from app.modules.notifications.application.commands.create_due_notifications.command import (
    CreateDueNotificationsCommand,
)
from app.modules.notifications.domain.model import NotificationSettings
from app.modules.notifications.domain.schedule_rule import (
    NotificationScheduleRule,
    ScheduleRuleTargetKind,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.result import (
    ReceiptActivity,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.result import (
    ExpiringReceipt,
)
from app.modules.users.application.queries.list_user_registration_facts.result import (
    UserRegistrationFact,
)

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
    batch_size: int = 10,
    campaign_key: str | None = None,
) -> CreateDueNotificationsCommand:
    return CreateDueNotificationsCommand(
        target_date=target_date,
        now=now,
        campaign_key=campaign_key,
        dry_run=dry_run,
        batch_size=batch_size,
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
    user_id: UUID = USER_ID,
    receipt_id: UUID = RECEIPT_ID,
    expires_on: date = date(2026, 7, 16),
    created_at: datetime = NOW - timedelta(days=1),
    days_until_expiry: int = 7,
    item_name: str = "공기청정기",
) -> ExpiringReceipt:
    return ExpiringReceipt(
        user_id=user_id,
        receipt_id=receipt_id,
        item_name=item_name,
        expires_on=expires_on,
        created_at=created_at,
        days_until_expiry=days_until_expiry,
    )


def user_candidate(
    *,
    user_id: UUID,
    days_since_joined: int,
) -> UserRegistrationFact:
    created_at = NOW - timedelta(days=days_since_joined)
    return UserRegistrationFact(
        user_id=user_id,
        registered_at=created_at,
    )


def activity_candidate(
    *,
    user_id: UUID,
    receipt_count: int = 0,
    last_receipt_created_at: datetime | None = None,
) -> ReceiptActivity:
    return ReceiptActivity(
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


def assert_no_scheduler_internal_metadata(metadata: Mapping[str, str]) -> None:
    internal_keys = {
        "campaignKey",
        "campaignPolicy",
        "deliveryHistory",
        "occurrenceId",
        "scheduledKey",
        "targetId",
        "targetType",
        "campaign_key",
        "campaign_policy",
        "delivery_history",
        "occurrence_id",
        "scheduled_key",
        "target_id",
        "target_type",
    }
    assert internal_keys.isdisjoint(metadata)
