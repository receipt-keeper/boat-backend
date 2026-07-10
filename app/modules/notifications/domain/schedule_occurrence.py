from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import assert_never
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.notifications.domain.schedule_rule import ScheduleRuleTargetKind


class ScheduleOccurrenceTargetType(StrEnum):
    RECEIPT = "receipt"
    USER = "user"


@dataclass(frozen=True, slots=True)
class ScheduleOccurrenceKey:
    campaign_key: str
    target_type: ScheduleOccurrenceTargetType
    target_id: UUID
    occurrence_on: date

    @classmethod
    def create(
        cls,
        *,
        campaign_key: str,
        target_type: str,
        target_id: UUID,
        occurrence_on: date,
    ) -> "ScheduleOccurrenceKey":
        _validate_campaign_key(campaign_key)
        return cls(
            campaign_key=campaign_key,
            target_type=_target_type(target_type),
            target_id=target_id,
            occurrence_on=occurrence_on,
        )


def _validate_campaign_key(value: str) -> None:
    if not value or value.strip() != value or len(value) > 100:
        raise ValidationError(
            [ErrorDetail(field="campaignKey", message="예약 알림 캠페인 키가 올바르지 않습니다.")]
        )


def _target_type(value: str) -> ScheduleOccurrenceTargetType:
    try:
        return ScheduleOccurrenceTargetType(value)
    except ValueError as exc:
        raise ValidationError(
            [ErrorDetail(field="targetType", message="예약 알림 대상 리소스가 올바르지 않습니다.")]
        ) from exc


def target_type_for_kind(target_kind: ScheduleRuleTargetKind) -> ScheduleOccurrenceTargetType:
    match target_kind:
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
            return ScheduleOccurrenceTargetType.RECEIPT
        case (
            ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT
            | ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT
            | ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER
        ):
            return ScheduleOccurrenceTargetType.USER
        case _ as unreachable:
            assert_never(unreachable)
