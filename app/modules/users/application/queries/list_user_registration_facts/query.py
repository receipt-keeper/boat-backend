from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError

_INVALID_BATCH_SIZE = "사용자 등록 사실 조회 batchSize가 올바르지 않습니다."
_INVALID_CURSOR = "사용자 등록 사실 조회 cursor가 올바르지 않습니다."
_INVALID_REGISTERED_WINDOW = "사용자 등록 시각 범위가 올바르지 않습니다."


@dataclass(frozen=True, slots=True)
class UserRegistrationFactCursor:
    registered_at: datetime
    user_id: UUID

    def __post_init__(self) -> None:
        if not _is_aware_datetime(self.registered_at) or not isinstance(self.user_id, UUID):
            raise ValidationError([ErrorDetail(field="cursor", message=_INVALID_CURSOR)])


@dataclass(frozen=True, slots=True)
class ListUserRegistrationFactsQuery:
    batch_size: int
    cursor: UserRegistrationFactCursor | None = None
    registered_after: datetime | None = None
    registered_before: datetime | None = None

    def __post_init__(self) -> None:
        details: list[ErrorDetail] = []
        if self.batch_size < 1:
            details.append(ErrorDetail(field="batchSize", message=_INVALID_BATCH_SIZE))
        if self.registered_after is not None and not _is_aware_datetime(self.registered_after):
            details.append(ErrorDetail(field="registeredAfter", message=_INVALID_REGISTERED_WINDOW))
        if self.registered_before is not None and not _is_aware_datetime(self.registered_before):
            details.append(
                ErrorDetail(field="registeredBefore", message=_INVALID_REGISTERED_WINDOW)
            )
        if (
            self.registered_after is not None
            and self.registered_before is not None
            and _is_aware_datetime(self.registered_after)
            and _is_aware_datetime(self.registered_before)
            and self.registered_after >= self.registered_before
        ):
            details.append(ErrorDetail(field="registeredAt", message=_INVALID_REGISTERED_WINDOW))
        if details:
            raise ValidationError(details)


def _is_aware_datetime(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None
