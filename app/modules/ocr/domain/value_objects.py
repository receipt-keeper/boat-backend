from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.value_object import ValueObject


@dataclass(frozen=True)
class ItemName(ValueObject[str]):
    def validate(self) -> None:
        if not self.value or not self.value.strip():
            raise ValidationError([ErrorDetail(field="item_name", message="제품명은 필수입니다.")])


@dataclass(frozen=True)
class BrandName(ValueObject[str]):
    def validate(self) -> None:
        if not self.value.strip():
            raise ValidationError(
                [ErrorDetail(field="brand_name", message="브랜드명은 비어 있을 수 없습니다.")]
            )


@dataclass(frozen=True)
class PaymentLocation(ValueObject[str]):
    def validate(self) -> None:
        if not self.value.strip():
            raise ValidationError(
                [ErrorDetail(field="payment_location", message="구매처는 비어 있을 수 없습니다.")]
            )


@dataclass(frozen=True)
class PaymentDate(ValueObject[date]):
    def validate(self) -> None:
        if self.value > date.today():
            raise ValidationError(
                [ErrorDetail(field="payment_date", message="구매일은 미래 날짜일 수 없습니다.")]
            )


@dataclass(frozen=True)
class WarrantyPeriodMonths(ValueObject[int]):
    MIN_MONTHS: ClassVar[int] = 1
    MAX_MONTHS: ClassVar[int] = 60

    def validate(self) -> None:
        if not (self.MIN_MONTHS <= self.value <= self.MAX_MONTHS):
            message = (
                f"무상 AS 기간은 {self.MIN_MONTHS}개월 이상 {self.MAX_MONTHS}개월 이하여야 합니다."
            )
            raise ValidationError([ErrorDetail(field="period_months", message=message)])


@dataclass(frozen=True)
class TotalAmount(ValueObject[int]):
    def validate(self) -> None:
        if self.value < 0:
            raise ValidationError(
                [ErrorDetail(field="total_amount", message="총 금액은 음수일 수 없습니다.")]
            )
