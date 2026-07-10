from dataclasses import dataclass
from datetime import time
from typing import Final


@dataclass(frozen=True, slots=True)
class ScheduleRuleSeed:
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


_SEND_TIME_LOCAL: Final = time(9, 0)


def _warranty(
    campaign_key: str,
    title_template: str,
    day_offset: int,
    body_template: str,
) -> ScheduleRuleSeed:
    return ScheduleRuleSeed(
        campaign_key=campaign_key,
        enabled=True,
        target_kind="warranty_receipt",
        day_offset=day_offset,
        first_delay_days=None,
        repeat_interval_days=None,
        lookback_days=None,
        send_time_local=_SEND_TIME_LOCAL,
        requires_marketing_consent=False,
        title_template=title_template,
        body_template=body_template,
    )


def _engagement(
    campaign_key: str,
    title_template: str,
    target_kind: str,
    first_delay_days: int | None,
    repeat_interval_days: int,
    lookback_days: int | None,
    body_template: str,
) -> ScheduleRuleSeed:
    return ScheduleRuleSeed(
        campaign_key=campaign_key,
        enabled=True,
        target_kind=target_kind,
        day_offset=None,
        first_delay_days=first_delay_days,
        repeat_interval_days=repeat_interval_days,
        lookback_days=lookback_days,
        send_time_local=_SEND_TIME_LOCAL,
        requires_marketing_consent=True,
        title_template=title_template,
        body_template=body_template,
    )


DEFAULT_NOTIFICATION_SCHEDULE_RULE_SEEDS: Final[tuple[ScheduleRuleSeed, ...]] = (
    _warranty(
        "warranty_caution_d30",
        "보증 주의",
        30,
        "[기기명] 무상 AS 30일 남았어요! 만료 전 서비스 센터 접수를 예약해보세요.",
    ),
    _warranty(
        "warranty_warning_d14",
        "보증 경고",
        14,
        "[기기명] 무상 AS 14일 남았어요! 기간 지나기 전 영수증 증빙 서류를 챙기세요.",
    ),
    _warranty(
        "warranty_risk_d7",
        "보증 위험",
        7,
        "[기기명] 무상 AS 7일 남았어요! 일주일 뒤에는 무상 수리가 어려우니 서두르세요.",
    ),
    _warranty(
        "warranty_expired_d0",
        "보증 완료",
        0,
        "[기기명] 무상 AS 오늘이 만료예요! 마지막 무상 혜택 기회를 놓치지 마세요.",
    ),
    _engagement(
        "engagement_unregistered_receipt_after_7d",
        "상시 유도 1",
        "engagement_unregistered_receipt",
        7,
        7,
        None,
        "지갑 속에 방치해둔 가전제품 영수증이 있나요? 지금 등록하고 보증 기간을 챙기세요!",
    ),
    _engagement(
        "engagement_inactive_receipt_7d",
        "상시 유도 2",
        "engagement_inactive_receipt",
        None,
        7,
        7,
        "최근에 새로 구매한 전자기기가 있으신가요? 영수증 한 장으로 AS 만료일을 관리해보세요.",
    ),
    _engagement(
        "engagement_all_users_14d",
        "상시 유도 3",
        "engagement_all_user",
        14,
        14,
        None,
        "지금 사용 가능한 무료 영수증 분석 기회가 남아있어요! 서랍 속 영수증을 스캔해보세요.",
    ),
)
