from datetime import UTC, date, datetime, time

import pytest

from app.core.domain.exceptions import ValidationError
from app.modules.notifications.domain.due_notification import (
    SYSTEM_TIMEZONE,
    DueNotificationRule,
    delivery_contract_for,
    matches_join_cadence,
    matches_receipt_activity,
    receipt_activity_since_for,
    registration_age_days_on,
    render_notification_text,
    resolve_due_notification_rule,
)
from app.modules.notifications.domain.schedule_rule import (
    NotificationScheduleRule,
    ScheduleRuleTargetKind,
)
from app.modules.notifications.domain.value_objects import NotificationMessageType


def test_resolve_due_notification_rule_uses_kst_current_date_without_scheduled_for() -> None:
    # Given: UTC 기준 전날 15:00과 자정 KST 발송 규칙이 있다.
    rule = _warranty_rule(send_time_local=time(0, 0))

    # When: target_date 없이 due rule을 해석한다.
    due_rule = resolve_due_notification_rule(
        rule=rule,
        now=datetime(2026, 7, 8, 15, 0, tzinfo=UTC),
        target_date=None,
    )

    # Then: UTC 날짜가 아니라 KST 현재 날짜를 쓰며 scheduled_for 상태는 보관하지 않는다.
    assert due_rule is not None
    assert due_rule.target_date == date(2026, 7, 9)
    assert not hasattr(due_rule, "scheduled_for")


def test_resolve_due_notification_rule_allows_historical_backfill() -> None:
    # Given: 이미 지난 KST target_date와 현재 local send time 전 시각이 있다.
    rule = _warranty_rule(send_time_local=time(9, 0))

    # When: historical target_date를 해석한다.
    due_rule = resolve_due_notification_rule(
        rule=rule,
        now=datetime(2026, 7, 10, 0, 0, tzinfo=UTC),
        target_date=date(2026, 7, 9),
    )

    # Then: historical backfill은 현재 send-time gate와 무관하게 due다.
    assert due_rule is not None
    assert due_rule.target_date == date(2026, 7, 9)


def test_resolve_due_notification_rule_is_noop_for_future_target_date() -> None:
    # Given: 현재 KST 날짜보다 미래인 target_date가 있다.
    rule = _warranty_rule(send_time_local=time(9, 0))

    # When: future target_date를 해석한다.
    due_rule = resolve_due_notification_rule(
        rule=rule,
        now=datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
        target_date=date(2026, 7, 11),
    )

    # Then: 미래 날짜는 notification scheduling 대상이 아니다.
    assert due_rule is None


def test_resolve_due_notification_rule_waits_for_local_send_time_today() -> None:
    # Given: KST 09:00 발송 규칙과 KST 08:59 현재 시각이 있다.
    rule = _warranty_rule(send_time_local=time(9, 0))

    # When: 오늘 KST target_date를 해석한다.
    due_rule = resolve_due_notification_rule(
        rule=rule,
        now=datetime(2026, 7, 8, 23, 59, tzinfo=UTC),
        target_date=date(2026, 7, 9),
    )

    # Then: local send-time 전에는 due가 아니다.
    assert due_rule is None


def test_resolve_due_notification_rule_rejects_naive_now() -> None:
    # Given: timezone 정보를 잃은 naive now가 있다.
    rule = _warranty_rule(send_time_local=time(9, 0))

    # When/Then: Asia/Seoul 기준을 확정할 수 없으므로 domain validation이 거부한다.
    with pytest.raises(ValidationError) as exc_info:
        resolve_due_notification_rule(
            rule=rule,
            now=datetime(2026, 7, 9, 9, 0),
            target_date=date(2026, 7, 9),
        )

    assert tuple((detail.field, detail.message) for detail in exc_info.value.details) == (
        ("now", "예약 알림 기준 시각이 올바르지 않습니다."),
    )


@pytest.mark.parametrize(
    ("target_kind", "message_type", "kind", "resource_type"),
    [
        (
            ScheduleRuleTargetKind.WARRANTY_RECEIPT,
            NotificationMessageType.TRANSACTIONAL,
            "warranty_expiry",
            "receipt",
        ),
        (
            ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT,
            NotificationMessageType.MARKETING,
            "receipt_registration_reminder",
            None,
        ),
        (
            ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT,
            NotificationMessageType.MARKETING,
            "receipt_inactivity_reminder",
            None,
        ),
        (
            ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER,
            NotificationMessageType.MARKETING,
            "receipt_analysis_reminder",
            None,
        ),
    ],
)
def test_delivery_contract_for_target_kind(
    target_kind: ScheduleRuleTargetKind,
    message_type: NotificationMessageType,
    kind: str,
    resource_type: str | None,
) -> None:
    # Given: 지원되는 schedule target kind가 있다.

    # When: 외부 notification delivery contract를 해석한다.
    contract = delivery_contract_for(target_kind)

    # Then: message type, external kind, resource type이 target kind별로 고정된다.
    assert contract.message_type == message_type
    assert contract.kind == kind
    assert contract.resource_type == resource_type


def test_delivery_contract_covers_every_schedule_target_kind() -> None:
    # Given: 현재 domain이 지원하는 모든 target kind가 있다.

    # When: 각 target kind의 delivery contract를 해석한다.
    contracts = tuple(delivery_contract_for(target_kind) for target_kind in ScheduleRuleTargetKind)

    # Then: enum에 target kind가 추가되면 누락 branch가 즉시 드러난다.
    assert len(contracts) == len(ScheduleRuleTargetKind)


def test_matches_join_cadence_uses_first_delay_and_repeat_interval() -> None:
    # Given: 가입 14일 후부터 14일마다 발송하는 engagement rule이 있다.
    rule = _engagement_rule(first_delay_days=14, repeat_interval_days=14, lookback_days=None)

    # When: 가입 경과일별 cadence를 판정한다.
    matches = tuple(
        matches_join_cadence(rule=rule, days_since_joined=days) for days in (13, 14, 28)
    )

    # Then: first delay 전은 제외하고 cadence date만 포함한다.
    assert matches == (False, True, True)


def test_matches_join_cadence_falls_back_to_lookback_days() -> None:
    # Given: first delay 없이 lookback days를 cadence 시작점으로 쓰는 activity rule이 있다.
    rule = _engagement_rule(first_delay_days=None, repeat_interval_days=7, lookback_days=7)

    # When: 가입 7일과 8일의 cadence를 판정한다.
    matches = tuple(matches_join_cadence(rule=rule, days_since_joined=days) for days in (7, 8))

    # Then: lookback days가 첫 cadence 기준일이 된다.
    assert matches == (True, False)


@pytest.mark.parametrize(
    ("target_date", "registered_at", "expected_days"),
    [
        (date(2026, 7, 9), datetime(2026, 7, 8, 14, 59, tzinfo=UTC), 1),
        (date(2026, 7, 9), datetime(2026, 7, 8, 15, 0, tzinfo=UTC), 0),
        (date(2026, 7, 9), datetime(2026, 7, 9, 15, 0, tzinfo=UTC), -1),
    ],
)
def test_registration_age_days_on_uses_kst_date_and_preserves_signed_days(
    target_date: date,
    registered_at: datetime,
    expected_days: int,
) -> None:
    assert (
        registration_age_days_on(
            target_date=target_date,
            registered_at=registered_at,
        )
        == expected_days
    )


@pytest.mark.parametrize(
    ("target_kind", "receipt_count", "expected"),
    [
        (ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT, 0, True),
        (ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT, 1, False),
        (ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT, 0, False),
        (ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT, 1, True),
        (ScheduleRuleTargetKind.WARRANTY_RECEIPT, 0, False),
        (ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER, 0, False),
    ],
)
def test_matches_receipt_activity(
    target_kind: ScheduleRuleTargetKind,
    receipt_count: int,
    expected: bool,
) -> None:
    # Given: target kind와 receipt activity count가 있다.

    # When: receipt activity 정책을 판정한다.
    matches = matches_receipt_activity(target_kind=target_kind, receipt_count=receipt_count)

    # Then: receipt registration engagement 종류만 count 조건에 따라 match된다.
    assert matches is expected


def test_receipt_activity_since_for_returns_none_for_unregistered_receipt_rule() -> None:
    since = receipt_activity_since_for(
        _due_rule(
            _engagement_rule(
                first_delay_days=7,
                repeat_interval_days=7,
                lookback_days=None,
                target_kind=ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT,
            )
        )
    )

    assert since is None


def test_receipt_activity_since_for_uses_kst_midnight_for_inactive_receipt_rule() -> None:
    since = receipt_activity_since_for(
        _due_rule(
            _engagement_rule(
                first_delay_days=None,
                repeat_interval_days=7,
                lookback_days=7,
                target_kind=ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT,
            )
        )
    )

    assert since == datetime(2026, 7, 2, 0, 0, tzinfo=SYSTEM_TIMEZONE)


def test_receipt_activity_since_for_rejects_inactive_rule_without_lookback_days() -> None:
    due_rule = _due_rule(
        _engagement_rule(
            first_delay_days=None,
            repeat_interval_days=7,
            lookback_days=None,
            target_kind=ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT,
        )
    )

    with pytest.raises(
        RuntimeError, match=r"비활성 영수증 유도 예약 규칙에 lookbackDays가 필요합니다."
    ):
        receipt_activity_since_for(due_rule)


def test_receipt_activity_since_for_rejects_warranty_rule() -> None:
    with pytest.raises(RuntimeError, match=r"영수증 활동 조회 대상이 아닌 예약 규칙입니다."):
        receipt_activity_since_for(_due_rule(_warranty_rule(send_time_local=time(9, 0))))


def test_receipt_activity_since_for_rejects_all_user_rule() -> None:
    due_rule = _due_rule(
        _engagement_rule(
            first_delay_days=14,
            repeat_interval_days=14,
            lookback_days=None,
            target_kind=ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER,
        )
    )

    with pytest.raises(RuntimeError, match=r"영수증 활동 조회 대상이 아닌 예약 규칙입니다."):
        receipt_activity_since_for(due_rule)


def test_render_notification_text_replaces_item_name_placeholder() -> None:
    # Given: [기기명] placeholder가 있는 notification template이 있다.

    # When: item name으로 template을 렌더링한다.
    rendered = render_notification_text("[기기명] 보증이 7일 남았어요.", item_name="노트북")

    # Then: user-visible text에 item name이 반영된다.
    assert rendered == "노트북 보증이 7일 남았어요."


def _warranty_rule(*, send_time_local: time) -> NotificationScheduleRule:
    return NotificationScheduleRule.create(
        campaign_key="warranty_risk_d7",
        enabled=True,
        target_kind=ScheduleRuleTargetKind.WARRANTY_RECEIPT,
        day_offset=7,
        first_delay_days=None,
        repeat_interval_days=None,
        lookback_days=None,
        send_time_local=send_time_local,
        requires_marketing_consent=False,
        title_template="[기기명] 보증 위험",
        body_template="[기기명] 보증이 7일 남았어요.",
    )


def _engagement_rule(
    *,
    first_delay_days: int | None,
    repeat_interval_days: int,
    lookback_days: int | None,
    target_kind: ScheduleRuleTargetKind = ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER,
) -> NotificationScheduleRule:
    return NotificationScheduleRule.create(
        campaign_key="engagement_all_users",
        enabled=True,
        target_kind=target_kind,
        day_offset=None,
        first_delay_days=first_delay_days,
        repeat_interval_days=repeat_interval_days,
        lookback_days=lookback_days,
        send_time_local=time(9, 0),
        requires_marketing_consent=True,
        title_template="상시 유도",
        body_template="영수증을 등록하세요.",
    )


def _due_rule(rule: NotificationScheduleRule) -> DueNotificationRule:
    return DueNotificationRule(rule=rule, target_date=date(2026, 7, 9))
