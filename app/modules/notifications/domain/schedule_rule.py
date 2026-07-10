from dataclasses import dataclass
from datetime import time
from enum import StrEnum
from typing import assert_never

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.validation import Notification as ValidationNotification


class ScheduleRuleTargetKind(StrEnum):
    WARRANTY_RECEIPT = "warranty_receipt"
    ENGAGEMENT_UNREGISTERED_RECEIPT = "engagement_unregistered_receipt"
    ENGAGEMENT_INACTIVE_RECEIPT = "engagement_inactive_receipt"
    ENGAGEMENT_ALL_USER = "engagement_all_user"


_ENGAGEMENT_TARGET_KINDS = frozenset(
    {
        ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT,
        ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT,
        ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER,
    }
)


@dataclass(frozen=True, slots=True)
class NotificationScheduleRule:
    campaign_key: str
    enabled: bool
    target_kind: ScheduleRuleTargetKind
    day_offset: int | None
    first_delay_days: int | None
    repeat_interval_days: int | None
    lookback_days: int | None
    send_time_local: time
    requires_marketing_consent: bool
    title_template: str
    body_template: str

    @classmethod
    def create(
        cls,
        *,
        campaign_key: str,
        enabled: bool,
        target_kind: str,
        day_offset: int | None,
        first_delay_days: int | None,
        repeat_interval_days: int | None,
        lookback_days: int | None,
        send_time_local: time,
        requires_marketing_consent: bool,
        title_template: str,
        body_template: str,
    ) -> "NotificationScheduleRule":
        notification = ValidationNotification()
        notification.collect(lambda: _validate_campaign_key(campaign_key))
        notification.collect(lambda: _validate_optional_non_negative("dayOffset", day_offset))
        notification.collect(
            lambda: _validate_optional_non_negative("firstDelayDays", first_delay_days)
        )
        notification.collect(
            lambda: _validate_optional_non_negative(
                "repeatIntervalDays",
                repeat_interval_days,
            )
        )
        notification.collect(lambda: _validate_optional_non_negative("lookbackDays", lookback_days))
        notification.collect(
            lambda: _validate_text(
                "titleTemplate",
                title_template,
                100,
                "예약 알림 제목 템플릿이 올바르지 않습니다.",
            )
        )
        notification.collect(
            lambda: _validate_text(
                "bodyTemplate",
                body_template,
                255,
                "예약 알림 본문 템플릿이 올바르지 않습니다.",
            )
        )
        new_target_kind = notification.collect(lambda: _target_kind(target_kind))
        notification.raise_if_any()
        _validate_timing_rule(
            target_kind=new_target_kind,
            day_offset=day_offset,
            repeat_interval_days=repeat_interval_days,
        )
        _validate_engagement_consent(
            target_kind=new_target_kind,
            requires_marketing_consent=requires_marketing_consent,
        )

        return cls(
            campaign_key=campaign_key,
            enabled=enabled,
            target_kind=new_target_kind,
            day_offset=day_offset,
            first_delay_days=first_delay_days,
            repeat_interval_days=repeat_interval_days,
            lookback_days=lookback_days,
            send_time_local=send_time_local,
            requires_marketing_consent=requires_marketing_consent,
            title_template=title_template,
            body_template=body_template,
        )


def _validate_campaign_key(value: str) -> None:
    _validate_text("campaignKey", value, 100, "예약 알림 캠페인 키가 올바르지 않습니다.")


def _validate_text(field: str, value: str, max_length: int, message: str) -> None:
    if not value or value.strip() != value or len(value) > max_length:
        raise ValidationError([ErrorDetail(field=field, message=message)])


def _validate_optional_non_negative(field: str, value: int | None) -> None:
    if value is not None and value < 0:
        raise ValidationError(
            [ErrorDetail(field=field, message="예약 알림 일수 값이 올바르지 않습니다.")]
        )


def _target_kind(value: str) -> ScheduleRuleTargetKind:
    try:
        return ScheduleRuleTargetKind(value)
    except ValueError as exc:
        raise ValidationError(
            [ErrorDetail(field="targetKind", message="예약 알림 대상 유형이 올바르지 않습니다.")]
        ) from exc


def _validate_timing_rule(
    *,
    target_kind: ScheduleRuleTargetKind,
    day_offset: int | None,
    repeat_interval_days: int | None,
) -> None:
    match target_kind:
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
            if day_offset is None:
                raise ValidationError(
                    [
                        ErrorDetail(
                            field="dayOffset",
                            message="보증 알림 예약 규칙에는 D-day offset이 필요합니다.",
                        )
                    ]
                )
        case (
            ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT
            | ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT
            | ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER
        ):
            if repeat_interval_days is None:
                raise ValidationError(
                    [
                        ErrorDetail(
                            field="repeatIntervalDays",
                            message="상시 유도 예약 규칙에는 반복 간격이 필요합니다.",
                        )
                    ]
                )
        case unreachable:
            assert_never(unreachable)


def _validate_engagement_consent(
    *,
    target_kind: ScheduleRuleTargetKind,
    requires_marketing_consent: bool,
) -> None:
    if target_kind in _ENGAGEMENT_TARGET_KINDS and not requires_marketing_consent:
        raise ValidationError(
            [
                ErrorDetail(
                    field="requiresMarketingConsent",
                    message="상시 유도 알림 예약 규칙은 마케팅 수신 동의가 필요합니다.",
                )
            ]
        )
