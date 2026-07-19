from dataclasses import dataclass
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.credits.domain import CreditAmount, CreditReason, CreditSourceType


@dataclass(frozen=True, slots=True)
class GrantCreditCommand:
    user_id: UUID
    amount: CreditAmount
    reason: CreditReason
    source_type: CreditSourceType | None = None
    source_id: UUID | None = None
    idempotency_key: str | None = None
    required_remaining_count: int | None = None

    def __post_init__(self) -> None:
        if (self.source_type is None) != (self.source_id is None):
            raise ValidationError(
                [
                    ErrorDetail(
                        field="source",
                        message="크레딧 출처 유형과 출처 ID는 함께 전달해야 합니다.",
                    )
                ]
            )
        if self.required_remaining_count is not None and self.required_remaining_count < 0:
            raise ValidationError(
                [
                    ErrorDetail(
                        field="required_remaining_count",
                        message="필수 잔여 크레딧 횟수는 0 이상이어야 합니다.",
                    )
                ]
            )
