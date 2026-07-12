import calendar
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from app.core.domain.entity import Entity
from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.validation import Notification
from app.modules.receipts.domain.value_objects import (
    ItemName,
    PaymentDate,
    ReceiptFileReferences,
    ReceiptStatusFilter,
    TotalAmount,
    WarrantyPeriodMonths,
)

DEFAULT_WARRANTY_PERIOD_MONTHS = 12


@dataclass(eq=False)
class Receipt(Entity[UUID]):
    user_id: UUID
    item_name: ItemName
    brand_name: str | None
    serial_number: str | None
    payment_location: str | None
    payment_date: PaymentDate
    total_amount: TotalAmount | None
    period_months: WarrantyPeriodMonths
    expires_on: date
    category: str | None
    sub_category: str | None
    memo: str | None
    requires_physical_receipt: bool
    receipt_file_ids: tuple[UUID, ...]

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        item_name: str | None,
        payment_date: date | None,
        receipt_id: UUID | None = None,
        brand_name: str | None = None,
        serial_number: str | None = None,
        payment_location: str | None = None,
        total_amount: int | None = None,
        period_months: int | None = None,
        expires_on: date | None = None,
        category: str | None = None,
        sub_category: str | None = None,
        memo: str | None = None,
        requires_physical_receipt: bool | None = False,
        receipt_file_ids: tuple[UUID, ...] | None = None,
    ) -> "Receipt":
        resolved_period_months = (
            DEFAULT_WARRANTY_PERIOD_MONTHS if period_months is None else period_months
        )

        notification = Notification()
        new_item_name = notification.collect(lambda: _required_item_name(item_name))
        new_payment_date = notification.collect(lambda: _required_payment_date(payment_date))
        new_total_amount = (
            None
            if total_amount is None
            else notification.collect(lambda: TotalAmount(total_amount))
        )
        new_period_months = notification.collect(
            lambda: WarrantyPeriodMonths(resolved_period_months)
        )
        new_brand_name = notification.collect(
            lambda: _optional_text(
                value=brand_name,
                field="brand_name",
                label="브랜드명",
                max_length=255,
            )
        )
        new_serial_number = notification.collect(
            lambda: _optional_text(
                value=serial_number,
                field="serial_number",
                label="시리얼 넘버",
                max_length=255,
            )
        )
        new_payment_location = notification.collect(
            lambda: _optional_text(
                value=payment_location,
                field="payment_location",
                label="구매처",
                max_length=500,
            )
        )
        new_category = notification.collect(
            lambda: _optional_text(
                value=category,
                field="category",
                label="대분류 카테고리",
                max_length=100,
            )
        )
        new_sub_category = notification.collect(
            lambda: _optional_text(
                value=sub_category,
                field="sub_category",
                label="소분류 카테고리",
                max_length=100,
            )
        )
        new_memo = notification.collect(
            lambda: _optional_text(
                value=memo,
                field="memo",
                label="메모",
                max_length=1000,
            )
        )
        new_requires_physical_receipt = notification.collect(
            lambda: _required_bool(
                value=requires_physical_receipt,
                field="requires_physical_receipt",
                label="실물 영수증 보관 필요 여부",
            )
        )
        new_file_references = notification.collect(
            lambda: _required_file_references(receipt_file_ids)
        )
        notification.raise_if_any()
        resolved_expires_on = _resolve_expires_on(
            explicit_expires_on=expires_on,
            payment_date=new_payment_date.value,
            period_months=new_period_months.value,
        )

        return cls(
            id=receipt_id or uuid4(),
            user_id=user_id,
            item_name=new_item_name,
            brand_name=new_brand_name,
            serial_number=new_serial_number,
            payment_location=new_payment_location,
            payment_date=new_payment_date,
            total_amount=new_total_amount,
            period_months=new_period_months,
            expires_on=resolved_expires_on,
            category=new_category,
            sub_category=new_sub_category,
            memo=new_memo,
            requires_physical_receipt=new_requires_physical_receipt,
            receipt_file_ids=new_file_references.value,
        )


def _required_item_name(value: str | None) -> ItemName:
    if value is None:
        raise ValidationError([ErrorDetail(field="item_name", message="제품명은 필수입니다.")])
    return ItemName(value.strip())


def _required_payment_date(value: date | None) -> PaymentDate:
    if value is None:
        raise ValidationError([ErrorDetail(field="payment_date", message="구매일은 필수입니다.")])
    return PaymentDate(value)


def _required_bool(*, value: bool | None, field: str, label: str) -> bool:
    if value is None:
        raise ValidationError([ErrorDetail(field=field, message=f"{label}는 필수입니다.")])
    return value


def _required_file_references(value: tuple[UUID, ...] | None) -> ReceiptFileReferences:
    if value is None:
        raise ValidationError(
            [
                ErrorDetail(
                    field="receipt_file_ids",
                    message="영수증 파일은 필수입니다.",
                )
            ]
        )
    return ReceiptFileReferences(value)


def _resolve_expires_on(
    *,
    explicit_expires_on: date | None,
    payment_date: date,
    period_months: int,
) -> date:
    if explicit_expires_on is None:
        return _add_months(payment_date, period_months)
    if explicit_expires_on < payment_date:
        raise ValidationError(
            [
                ErrorDetail(
                    field="expires_on",
                    message="보장 만료일은 구매일보다 빠를 수 없습니다.",
                )
            ]
        )
    return explicit_expires_on


def _optional_text(
    *,
    value: str | None,
    field: str,
    label: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > max_length:
        raise ValidationError(
            [
                ErrorDetail(
                    field=field,
                    message=f"{label}{_topic_particle(label)} {max_length}자 이하여야 합니다.",
                )
            ]
        )
    return stripped


def _topic_particle(label: str) -> str:
    last_character = label[-1]
    if not ("가" <= last_character <= "힣"):
        return "은"
    has_final_consonant = (ord(last_character) - ord("가")) % 28 != 0
    return "은" if has_final_consonant else "는"


def _add_months(start_date: date, months: int) -> date:
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(start_date.day, last_day)
    return date(year, month, day)


def warranty_d_day(expires_on: date, *, today: date | None = None) -> int:
    reference_date = today or date.today()
    return (expires_on - reference_date).days


def warranty_status(expires_on: date, *, today: date | None = None) -> ReceiptStatusFilter:
    d_day = warranty_d_day(expires_on, today=today)
    if d_day < 0:
        return ReceiptStatusFilter.EXPIRED
    if d_day <= 30:
        return ReceiptStatusFilter.EXPIRING
    return ReceiptStatusFilter.ACTIVE
