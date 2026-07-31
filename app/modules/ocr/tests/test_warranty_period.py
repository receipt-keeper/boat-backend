from datetime import date

import pytest

from app.core.domain.exceptions import ValidationError
from app.modules.ocr.domain.model import ReceiptOcrResult
from app.modules.ocr.domain.value_objects import WarrantyPeriodMonths


@pytest.mark.parametrize("value", [1, 60, 61, 99, 108, 120])
def test_ocr_warranty_period_accepts_receipt_contract_boundaries(value: int) -> None:
    assert WarrantyPeriodMonths(value).value == value


@pytest.mark.parametrize("value", [0, 121])
def test_ocr_warranty_period_rejects_out_of_range_values(value: int) -> None:
    with pytest.raises(ValidationError) as captured:
        WarrantyPeriodMonths(value)

    assert [(detail.field, detail.message) for detail in captured.value.details] == [
        (
            "period_months",
            "무상 AS 기간은 1개월 이상 120개월 이하여야 합니다.",
        )
    ]


def test_ocr_result_calculates_expiration_at_120_month_boundary() -> None:
    result = ReceiptOcrResult.create(
        item_name="장기 보증 제품",
        brand_name=None,
        serial_number=None,
        payment_location=None,
        payment_date=date(2024, 1, 31),
        total_amount=None,
        period_months=120,
        category=None,
        sub_category=None,
    )

    assert result.period_months.value == 120
    assert result.expires_on == date(2034, 1, 31)
