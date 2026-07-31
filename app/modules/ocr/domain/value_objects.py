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
    MAX_MONTHS: ClassVar[int] = 120

    def validate(self) -> None:
        if not (self.MIN_MONTHS <= self.value <= self.MAX_MONTHS):
            message = (
                f"무상 AS 기간은 {self.MIN_MONTHS}개월 이상 {self.MAX_MONTHS}개월 이하여야 합니다."
            )
            raise ValidationError([ErrorDetail(field="period_months", message=message)])


@dataclass(frozen=True)
class TotalAmount(ValueObject[int]):
    MIN_AMOUNT: ClassVar[int] = 0
    MAX_AMOUNT: ClassVar[int] = 999_999_999

    def validate(self) -> None:
        if not (self.MIN_AMOUNT <= self.value <= self.MAX_AMOUNT):
            raise ValidationError(
                [
                    ErrorDetail(
                        field="total_amount",
                        message="구매가격은 0원 이상 999,999,999원 이하로 입력해 주세요.",
                    )
                ]
            )
