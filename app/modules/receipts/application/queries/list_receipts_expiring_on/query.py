from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError

_INVALID_OFFSET_DAYS = "보증 알림 후보 조회 offsetDays가 올바르지 않습니다."
_INVALID_BATCH_SIZE = "보증 알림 후보 조회 batchSize가 올바르지 않습니다."
_INVALID_TARGET_DATE = "만료 예정 영수증 조회 targetDate가 올바르지 않습니다."


@dataclass(frozen=True, slots=True)
class ListReceiptsExpiringOnQuery:
    target_date: date
    offset_days: int
    limit: int
    cursor_receipt_id: UUID | None = None

    def __post_init__(self) -> None:
        details: list[ErrorDetail] = []
        if type(self.target_date) is not date:
            details.append(ErrorDetail(field="targetDate", message=_INVALID_TARGET_DATE))
        if self.offset_days < 0:
            details.append(ErrorDetail(field="offsetDays", message=_INVALID_OFFSET_DAYS))
        if self.limit < 1:
            details.append(ErrorDetail(field="batchSize", message=_INVALID_BATCH_SIZE))
        if details:
            raise ValidationError(details)
