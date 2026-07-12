from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.value_object import ValueObject


class ReceiptStatusFilter(StrEnum):
    ALL = "all"
    ACTIVE = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"


class ReceiptSort(StrEnum):
    RECENT = "recent"
    EXPIRES_ON = "expiresOn"
    PURCHASE_DATE = "purchaseDate"
    TITLE = "title"


class ReceiptCategory(StrEnum):
    KITCHEN_APPLIANCE = "kitchen_appliance"
    LAUNDRY_CLEANING = "laundry_cleaning"
    LIVING_CLIMATE = "living_climate"
    IT_DEVICE = "it_device"
    OTHER_DEVICE = "other_device"

    @property
    def api_label(self) -> str:
        return _CATEGORY_API_LABELS[self]

    @classmethod
    def _missing_(cls, value: object) -> "ReceiptCategory | None":
        if not isinstance(value, str):
            return None
        return _CATEGORY_ALIASES.get(_category_alias_key(value))


_CATEGORY_API_LABELS: dict[ReceiptCategory, str] = {
    ReceiptCategory.KITCHEN_APPLIANCE: "주방 가전",
    ReceiptCategory.LAUNDRY_CLEANING: "세탁/청소",
    ReceiptCategory.LIVING_CLIMATE: "리빙/냉난방",
    ReceiptCategory.IT_DEVICE: "IT 기기",
    ReceiptCategory.OTHER_DEVICE: "기타 기기",
}


def _category_alias_key(value: str) -> str:
    return "".join(value.split()).lower()


_CATEGORY_ALIASES: dict[str, ReceiptCategory] = {
    _category_alias_key(category.value): category for category in ReceiptCategory
}
_CATEGORY_ALIASES.update(
    {
        "주방가전": ReceiptCategory.KITCHEN_APPLIANCE,
        "세탁/청소": ReceiptCategory.LAUNDRY_CLEANING,
        "세탁청소": ReceiptCategory.LAUNDRY_CLEANING,
        "리빙/냉난방": ReceiptCategory.LIVING_CLIMATE,
        "리빙냉난방": ReceiptCategory.LIVING_CLIMATE,
        "it기기": ReceiptCategory.IT_DEVICE,
        "it제품": ReceiptCategory.IT_DEVICE,
        "영상/it제품": ReceiptCategory.IT_DEVICE,
        "영상it제품": ReceiptCategory.IT_DEVICE,
        "기타기기": ReceiptCategory.OTHER_DEVICE,
        "기타제품": ReceiptCategory.OTHER_DEVICE,
        "기타": ReceiptCategory.OTHER_DEVICE,
    }
)


@dataclass(frozen=True, slots=True)
class ItemName(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        stripped = self.value.strip()
        if not stripped:
            raise ValidationError([ErrorDetail(field="item_name", message="제품명은 필수입니다.")])
        if len(stripped) > self.MAX_LENGTH:
            raise ValidationError(
                [
                    ErrorDetail(
                        field="item_name",
                        message=f"제품명은 {self.MAX_LENGTH}자 이하여야 합니다.",
                    )
                ]
            )


@dataclass(frozen=True, slots=True)
class PaymentDate(ValueObject[date]):
    def validate(self) -> None:
        if self.value > date.today():
            raise ValidationError(
                [ErrorDetail(field="payment_date", message="구매일은 미래 날짜일 수 없습니다.")]
            )


@dataclass(frozen=True, slots=True)
class TotalAmount(ValueObject[int]):
    def validate(self) -> None:
        if self.value < 0:
            raise ValidationError(
                [ErrorDetail(field="total_amount", message="총 결제 금액은 0 이상이어야 합니다.")]
            )


@dataclass(frozen=True, slots=True)
class WarrantyPeriodMonths(ValueObject[int]):
    MIN_MONTHS: ClassVar[int] = 1
    MAX_MONTHS: ClassVar[int] = 60

    def validate(self) -> None:
        if not (self.MIN_MONTHS <= self.value <= self.MAX_MONTHS):
            message = (
                f"무상 AS 기간은 {self.MIN_MONTHS}개월 이상 {self.MAX_MONTHS}개월 이하여야 합니다."
            )
            raise ValidationError([ErrorDetail(field="period_months", message=message)])


@dataclass(frozen=True, slots=True)
class ReceiptFileReferences(ValueObject[tuple[UUID, ...]]):
    MIN_COUNT: ClassVar[int] = 1
    MAX_COUNT: ClassVar[int] = 5

    def validate(self) -> None:
        if len(self.value) < self.MIN_COUNT:
            raise ValidationError(
                [
                    ErrorDetail(
                        field="receipt_file_ids",
                        message="영수증 파일은 최소 1개 이상 연결해야 합니다.",
                    )
                ]
            )
        if len(self.value) > self.MAX_COUNT:
            raise ValidationError(
                [
                    ErrorDetail(
                        field="receipt_file_ids",
                        message=f"영수증 파일은 최대 {self.MAX_COUNT}개까지 연결할 수 있습니다.",
                    )
                ]
            )
        if len(set(self.value)) != len(self.value):
            raise ValidationError(
                [
                    ErrorDetail(
                        field="receipt_file_ids",
                        message="중복된 영수증 파일은 연결할 수 없습니다.",
                    )
                ]
            )
