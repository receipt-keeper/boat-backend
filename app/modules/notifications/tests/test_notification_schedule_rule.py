from datetime import time
from typing import Protocol

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.domain.exceptions import ValidationError
from app.modules.notifications.application import schedule_rule_seed
from app.modules.notifications.domain import schedule_rule
from app.modules.notifications.infrastructure.persistence import (
    repository as persistence_repository,
)


class _ScheduleRule(Protocol):
    campaign_key: str
    enabled: bool
    target_kind: str
    day_offset: int | None
    first_delay_days: int | None
    repeat_interval_days: int | None
    lookback_days: int | None
    send_time_local: time
    requires_marketing_consent: bool
    title_template: str
    body_template: str


def test_default_schedule_rule_seed_matches_pm_campaign_table() -> None:
    # Given: PM 정책표를 seedable schedule rule artifact로 정의했다.
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
    rule_class = _schedule_rule_class()

    # When/Then: domain boundary가 한글 validation detail로 거부한다.
    with pytest.raises(ValidationError) as exc_info:
        rule_class.create(
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
    rule_class = _schedule_rule_class()

    # When/Then: scheduler가 해석할 수 없는 timing rule을 거부한다.
    with pytest.raises(ValidationError) as exc_info:
        rule_class.create(
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


async def test_repository_upserts_and_lists_default_schedule_rules(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 비어 있는 notification schedule rule table과 production seed가 있다.
    async with postgres_session_factory() as session:
        repository_class = _schedule_rule_repository_class()
        repository = repository_class(session)
        upsert_default_rules = _upsert_default_schedule_rules()

        # When: seed upsert를 같은 process에서 반복 실행한다.
        await upsert_default_rules(repository)
        await upsert_default_rules(repository)
        rules = await repository.list_all()

    # Then: 중복 없이 7개 schedule rule row가 복원된다.
    rule_by_key = {rule.campaign_key: rule for rule in rules}
    assert set(rule_by_key) == {rule.campaign_key for rule in _default_schedule_rules()}
    assert len(rules) == 7
    assert rule_by_key["warranty_caution_d30"].day_offset == 30
    assert rule_by_key["engagement_unregistered_receipt_after_7d"].first_delay_days == 7
    assert rule_by_key["engagement_unregistered_receipt_after_7d"].repeat_interval_days == 7
    assert rule_by_key["engagement_inactive_receipt_7d"].lookback_days == 7
    assert rule_by_key["engagement_all_users_14d"].first_delay_days == 14
    assert rule_by_key["engagement_all_users_14d"].repeat_interval_days == 14


def _default_schedule_rules() -> tuple[_ScheduleRule, ...]:
    rules = getattr(schedule_rule_seed, "DEFAULT_NOTIFICATION_SCHEDULE_RULES", None)
    assert rules is not None
    return rules


def _schedule_rule_class():
    rule_class = getattr(schedule_rule, "NotificationScheduleRule", None)
    assert rule_class is not None
    return rule_class


def _schedule_rule_repository_class():
    repository_class = getattr(
        persistence_repository,
        "SqlAlchemyNotificationScheduleRuleRepository",
        None,
    )
    assert repository_class is not None
    return repository_class


def _upsert_default_schedule_rules():
    upsert_default_rules = getattr(
        schedule_rule_seed,
        "upsert_default_notification_schedule_rules",
        None,
    )
    assert upsert_default_rules is not None
    return upsert_default_rules


def _validation_details(error: ValidationError) -> tuple[tuple[str, str], ...]:
    return tuple((detail.field, detail.message) for detail in error.details)
