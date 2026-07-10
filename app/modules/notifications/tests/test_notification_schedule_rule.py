from datetime import time

import pytest

from app.core.domain.exceptions import ValidationError
from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule


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


def test_schedule_rule_model_rejects_warranty_rule_with_engagement_timing_values() -> None:
    # Given: DB warranty timing constraint를 위반하는 engagement timing 값이 있다.

    # When/Then: persistence 전 domain factory가 각 잘못된 필드를 함께 거부한다.
    with pytest.raises(ValidationError) as exc_info:
        NotificationScheduleRule.create(
            campaign_key="warranty_invalid_timing",
            enabled=True,
            target_kind="warranty_receipt",
            day_offset=7,
            first_delay_days=1,
            repeat_interval_days=7,
            lookback_days=7,
            send_time_local=time(9, 0),
            requires_marketing_consent=False,
            title_template="테스트 제목",
            body_template="테스트 본문",
        )

    assert _validation_details(exc_info.value) == (
        ("firstDelayDays", "보증 알림 예약 규칙에는 D-day offset 외의 일정 값이 없어야 합니다."),
        (
            "repeatIntervalDays",
            "보증 알림 예약 규칙에는 D-day offset 외의 일정 값이 없어야 합니다.",
        ),
        ("lookbackDays", "보증 알림 예약 규칙에는 D-day offset 외의 일정 값이 없어야 합니다."),
    )


def _validation_details(error: ValidationError) -> tuple[tuple[str, str], ...]:
    return tuple((detail.field, detail.message) for detail in error.details)
