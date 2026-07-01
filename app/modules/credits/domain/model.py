from dataclasses import InitVar, dataclass
from datetime import datetime
from enum import StrEnum
from typing import assert_never
from uuid import UUID

from app.core.domain.entity import Entity
from app.core.domain.exceptions import ErrorDetail, ValidationError

_NON_NEGATIVE_COUNT_MESSAGE = "크레딧 횟수는 0 이상이어야 합니다."


class CreditReason(StrEnum):
    MONTHLY_OCR_ALLOWANCE = "monthlyOcrAllowance"
    EVENT_OCR_ALLOWANCE = "eventOcrAllowance"
    OCR_USAGE = "ocrUsage"


class FeatureKey(StrEnum):
    OCR = "ocr"


class CreditAction(StrEnum):
    GRANT = "grant"
    USE = "use"


@dataclass(frozen=True, slots=True)
class CreditCount:
    value: int
    field_name: InitVar[str] = "credit_count"

    def __post_init__(self, field_name: str) -> None:
        if self.value < 0:
            raise ValidationError(
                [
                    ErrorDetail(
                        field=field_name,
                        message=_NON_NEGATIVE_COUNT_MESSAGE,
                    )
                ]
            )


@dataclass(frozen=True, slots=True, init=False)
class CreditBalance:
    total_granted: CreditCount
    used: CreditCount
    remaining: CreditCount

    def __init__(
        self,
        *,
        total_granted_count: int | CreditCount,
        used_count: int | CreditCount,
        remaining_count: int | CreditCount,
    ) -> None:
        total_granted = _credit_count_for(
            total_granted_count,
            field_name="total_granted_count",
        )
        used = _credit_count_for(used_count, field_name="used_count")
        remaining = _credit_count_for(remaining_count, field_name="remaining_count")
        if total_granted.value != used.value + remaining.value:
            raise ValidationError(
                [
                    ErrorDetail(
                        field="total_granted_count",
                        message="전체 지급 횟수는 사용 횟수와 남은 횟수의 합과 같아야 합니다.",
                    )
                ]
            )
        object.__setattr__(self, "total_granted", total_granted)
        object.__setattr__(self, "used", used)
        object.__setattr__(self, "remaining", remaining)

    @property
    def total_granted_count(self) -> int:
        return self.total_granted.value

    @property
    def used_count(self) -> int:
        return self.used.value

    @property
    def remaining_count(self) -> int:
        return self.remaining.value

    def can_cover(self, amount: CreditCount) -> bool:
        return self.remaining.value >= amount.value


@dataclass(frozen=True, slots=True)
class CreditTransaction:
    feature_key: FeatureKey
    reason: CreditReason
    action: CreditAction
    amount: int
    created_at: datetime


@dataclass(eq=False)
class UserCredit(Entity[UUID]):
    feature_key: FeatureKey
    balance: CreditBalance

    @classmethod
    def restore(
        cls,
        *,
        user_id: UUID,
        feature_key: FeatureKey,
        total_granted_count: int,
        used_count: int,
        remaining_count: int,
    ) -> "UserCredit":
        balance = CreditBalance(
            total_granted_count=total_granted_count,
            used_count=used_count,
            remaining_count=remaining_count,
        )
        return cls(
            id=user_id,
            feature_key=feature_key,
            balance=balance,
        )

    @property
    def total_granted_count(self) -> int:
        return self.balance.total_granted_count

    @property
    def used_count(self) -> int:
        return self.balance.used_count

    @property
    def remaining_count(self) -> int:
        return self.balance.remaining_count

    def can_use(self, amount: int) -> bool:
        if amount <= 0:
            return False
        return self.balance.can_cover(CreditCount(value=amount, field_name="amount"))


def _credit_count_for(value: int | CreditCount, *, field_name: str) -> CreditCount:
    match value:
        case CreditCount():
            return value
        case int():
            return CreditCount(value=value, field_name=field_name)
        case unreachable:
            assert_never(unreachable)
