import calendar
from dataclasses import dataclass
from datetime import date

from app.core.domain.validation import Notification
from app.modules.ocr.domain.value_objects import (
    BrandName,
    ItemName,
    PaymentDate,
    PaymentLocation,
    TotalAmount,
    WarrantyPeriodMonths,
)

DEFAULT_WARRANTY_PERIOD_MONTHS = 12


@dataclass(frozen=True)
class ReceiptOcrResult:
    item_name: ItemName
    brand_name: BrandName | None
    payment_location: PaymentLocation | None
    payment_date: PaymentDate
    total_amount: TotalAmount | None
    period_months: WarrantyPeriodMonths
    expires_on: date
    warnings: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        item_name: str | None,
        brand_name: str | None,
        payment_location: str | None,
        payment_date: date | None,
        total_amount: int | None,
        period_months: int | None,
    ) -> "ReceiptOcrResult":
        warnings: list[str] = []
        resolved_payment_date = payment_date
        if resolved_payment_date is None:
            resolved_payment_date = date.today()
            warnings.append("구매일을 찾지 못해 오늘 날짜 기본값을 적용했습니다.")

        resolved_period_months = period_months
        if resolved_period_months is None:
            resolved_period_months = DEFAULT_WARRANTY_PERIOD_MONTHS
            warnings.append("무상 AS 기간을 찾지 못해 12개월 기본값을 적용했습니다.")

        notification = Notification()
        new_item_name = notification.collect(lambda: ItemName((item_name or "").strip()))
        new_payment_date = notification.collect(lambda: PaymentDate(resolved_payment_date))
        new_period_months = notification.collect(
            lambda: WarrantyPeriodMonths(resolved_period_months)
        )
        normalized_brand_name = _blank_to_none(brand_name)
        normalized_payment_location = _blank_to_none(payment_location)
        new_brand_name = (
            notification.collect(lambda: BrandName(normalized_brand_name))
            if normalized_brand_name is not None
            else None
        )
        new_payment_location = (
            notification.collect(lambda: PaymentLocation(normalized_payment_location))
            if normalized_payment_location is not None
            else None
        )
        new_total_amount = (
            notification.collect(lambda: TotalAmount(total_amount))
            if total_amount is not None
            else None
        )
        notification.raise_if_any()

        return cls(
            item_name=new_item_name,
            brand_name=new_brand_name,
            payment_location=new_payment_location,
            payment_date=new_payment_date,
            total_amount=new_total_amount,
            period_months=new_period_months,
            expires_on=_add_months(new_payment_date.value, new_period_months.value),
            warnings=tuple(warnings),
        )


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


def _add_months(start_date: date, months: int) -> date:
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(start_date.day, last_day)
    return date(year, month, day)
