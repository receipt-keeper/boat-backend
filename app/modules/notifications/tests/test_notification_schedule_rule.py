from datetime import time

import pytest

from app.core.domain.exceptions import ValidationError
from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule
from app.modules.notifications.schedule_rule_seed_data import (
    DEFAULT_NOTIFICATION_SCHEDULE_RULE_SEEDS,
    ScheduleRuleSeed,
)


def test_default_schedule_rule_seed_matches_pm_campaign_table() -> None:
    # Given: Alembic가 사용하는 schedule rule seed data를 domain factory에 전달한다.
    rules = _default_schedule_rules()
    rule_by_key = {rule.campaign_key: rule for rule in rules}

    # When: 기본 schedule rule seed를 확인한다.
    ordered_keys = tuple(rule.campaign_key for rule in rules)

    # Then: 캠페인 7종은 one row per schedule rule로 표현된다.
    assert ordered_keys == (
        "warranty_caution_d30",
        "warranty_warning_d14",
        "warranty_risk_d7",
        "warranty_expired_d0",
        "engagement_unregistered_receipt_after_7d",
        "engagement_inactive_receipt_7d",
        "engagement_all_users_14d",
    )
    assert rule_by_key["warranty_caution_d30"].target_kind == "warranty_receipt"
    assert rule_by_key["warranty_caution_d30"].day_offset == 30
    assert rule_by_key["warranty_warning_d14"].day_offset == 14
    assert rule_by_key["warranty_risk_d7"].day_offset == 7
    assert rule_by_key["warranty_expired_d0"].day_offset == 0
    assert rule_by_key["engagement_unregistered_receipt_after_7d"].target_kind == (
        "engagement_unregistered_receipt"
    )
    assert rule_by_key["engagement_unregistered_receipt_after_7d"].first_delay_days == 7
    assert rule_by_key["engagement_unregistered_receipt_after_7d"].repeat_interval_days == 7
    assert rule_by_key["engagement_inactive_receipt_7d"].target_kind == (
        "engagement_inactive_receipt"
    )
    assert rule_by_key["engagement_inactive_receipt_7d"].repeat_interval_days == 7
    assert rule_by_key["engagement_inactive_receipt_7d"].lookback_days == 7
    assert rule_by_key["engagement_all_users_14d"].target_kind == "engagement_all_user"
    assert rule_by_key["engagement_all_users_14d"].first_delay_days == 14
    assert rule_by_key["engagement_all_users_14d"].repeat_interval_days == 14
    assert all(rule.send_time_local == time(9, 0) for rule in rules)
    assert all(rule.enabled for rule in rules)
    assert all(
        not rule_by_key[key].requires_marketing_consent
        for key in (
            "warranty_caution_d30",
            "warranty_warning_d14",
            "warranty_risk_d7",
            "warranty_expired_d0",
        )
    )
    assert all(
        rule_by_key[key].requires_marketing_consent
        for key in (
            "engagement_unregistered_receipt_after_7d",
            "engagement_inactive_receipt_7d",
            "engagement_all_users_14d",
        )
    )


def test_schedule_rule_model_rejects_invalid_target_kind() -> None:
    # Given: 존재하지 않는 target_kind 값이 들어온다.

    # When/Then: domain boundary가 한글 validation detail로 거부한다.
    with pytest.raises(ValidationError) as exc_info:
        NotificationScheduleRule.create(
            campaign_key="invalid_target_kind",
            enabled=True,
            target_kind="settings",
            day_offset=1,
            first_delay_days=None,
            repeat_interval_days=None,
            lookback_days=None,
            send_time_local=time(9, 0),
            requires_marketing_consent=False,
            title_template="테스트 제목",
            body_template="테스트 본문",
        )

    assert _validation_details(exc_info.value) == (
        ("targetKind", "예약 알림 대상 유형이 올바르지 않습니다."),
    )


def test_schedule_rule_model_rejects_incomplete_timing_rule() -> None:
    # Given: warranty schedule rule이 day_offset 없이 정의된다.

    # When/Then: scheduler가 해석할 수 없는 timing rule을 거부한다.
    with pytest.raises(ValidationError) as exc_info:
        NotificationScheduleRule.create(
            campaign_key="warranty_missing_offset",
            enabled=True,
            target_kind="warranty_receipt",
            day_offset=None,
            first_delay_days=None,
            repeat_interval_days=None,
            lookback_days=None,
            send_time_local=time(9, 0),
            requires_marketing_consent=False,
            title_template="테스트 제목",
            body_template="테스트 본문",
        )

    assert _validation_details(exc_info.value) == (
        ("dayOffset", "보증 알림 예약 규칙에는 D-day offset이 필요합니다."),
    )


def _default_schedule_rules() -> tuple[NotificationScheduleRule, ...]:
    return tuple(_rule_from_seed(seed) for seed in DEFAULT_NOTIFICATION_SCHEDULE_RULE_SEEDS)


def _rule_from_seed(seed: ScheduleRuleSeed) -> NotificationScheduleRule:
    return NotificationScheduleRule.create(
        campaign_key=seed.campaign_key,
        enabled=seed.enabled,
        target_kind=seed.target_kind,
        day_offset=seed.day_offset,
        first_delay_days=seed.first_delay_days,
        repeat_interval_days=seed.repeat_interval_days,
        lookback_days=seed.lookback_days,
        send_time_local=seed.send_time_local,
        requires_marketing_consent=seed.requires_marketing_consent,
        title_template=seed.title_template,
        body_template=seed.body_template,
    )


def _validation_details(error: ValidationError) -> tuple[tuple[str, str], ...]:
    return tuple((detail.field, detail.message) for detail in error.details)
