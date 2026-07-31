import pytest

from app.core.domain.exceptions import ValidationError
from app.modules.receipts.domain.value_objects import TotalAmount, WarrantyPeriodMonths


@pytest.mark.parametrize("value", [0, 1, 999_999_999])
def test_total_amount_accepts_supported_boundaries(value: int) -> None:
    assert TotalAmount(value).value == value


@pytest.mark.parametrize("value", [-1, 1_000_000_000])
def test_total_amount_rejects_out_of_range_values_with_korean_message(value: int) -> None:
    with pytest.raises(ValidationError) as captured:
        TotalAmount(value)

    assert [(detail.field, detail.message) for detail in captured.value.details] == [
        (
            "total_amount",
            "구매가격은 0원 이상 999,999,999원 이하로 입력해 주세요.",
        )
    ]


def test_total_amount_restores_grandfathered_value_without_relaxing_new_validation() -> None:
    restored = TotalAmount.restore_grandfathered(1_000_000_000)

    assert restored.value == 1_000_000_000
    with pytest.raises(ValidationError):
        TotalAmount(1_000_000_000)


@pytest.mark.parametrize("value", [1, 60])
def test_warranty_period_accepts_current_write_boundaries(value: int) -> None:
    assert WarrantyPeriodMonths(value).value == value


def test_warranty_period_restores_future_value_without_relaxing_current_writes() -> None:
    restored = WarrantyPeriodMonths.restore_grandfathered(120)

    assert restored.value == 120
    with pytest.raises(ValidationError):
        WarrantyPeriodMonths(120)


@pytest.mark.parametrize("value", [0, 61, 121])
def test_warranty_period_rejects_out_of_range_values_with_korean_message(value: int) -> None:
    with pytest.raises(ValidationError) as captured:
        WarrantyPeriodMonths(value)

    assert [(detail.field, detail.message) for detail in captured.value.details] == [
        (
            "period_months",
            "무상 AS 기간은 1개월 이상 60개월 이하로 입력해 주세요.",
        )
    ]
