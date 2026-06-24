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
    TotalAmount,
    WarrantyPeriodMonths,
)

DEFAULT_WARRANTY_PERIOD_MONTHS = 12


@dataclass(eq=False)
class Receipt(Entity[UUID]):
    user_id: UUID
    item_name: ItemName
    brand_name: str | None
    payment_location: str | None
    payment_date: PaymentDate
    total_amount: TotalAmount | None
    period_months: WarrantyPeriodMonths
    expires_on: date
    category: str | None
    memo: str | None
    requires_physical_receipt: bool
    receipt_file_ids: tuple[UUID, ...]

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        item_name: str,
        payment_date: date,
        receipt_id: UUID | None = None,
        brand_name: str | None = None,
        payment_location: str | None = None,
        total_amount: int | None = None,
        period_months: int | None = None,
        category: str | None = None,
        memo: str | None = None,
        requires_physical_receipt: bool = False,
        receipt_file_ids: tuple[UUID, ...] = (),
    ) -> "Receipt":
        resolved_period_months = (
            DEFAULT_WARRANTY_PERIOD_MONTHS if period_months is None else period_months
        )

        notification = Notification()
        new_item_name = notification.collect(lambda: ItemName(item_name.strip()))
        new_payment_date = notification.collect(lambda: PaymentDate(payment_date))
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
        new_memo = notification.collect(
            lambda: _optional_text(
                value=memo,
                field="memo",
                label="메모",
                max_length=1000,
            )
        )
        new_file_references = notification.collect(lambda: ReceiptFileReferences(receipt_file_ids))
        notification.raise_if_any()

        return cls(
            id=receipt_id or uuid4(),
            user_id=user_id,
            item_name=new_item_name,
            brand_name=new_brand_name,
            payment_location=new_payment_location,
            payment_date=new_payment_date,
            total_amount=new_total_amount,
            period_months=new_period_months,
            expires_on=_add_months(new_payment_date.value, new_period_months.value),
            category=new_category,
            memo=new_memo,
            requires_physical_receipt=requires_physical_receipt,
            receipt_file_ids=new_file_references.value,
        )


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
            [ErrorDetail(field=field, message=f"{label}은 {max_length}자 이하여야 합니다.")]
        )
    return stripped


def _add_months(start_date: date, months: int) -> date:
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(start_date.day, last_day)
    return date(year, month, day)
