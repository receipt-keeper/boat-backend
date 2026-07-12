import pytest

from app.modules.receipts.domain.value_objects import ReceiptCategory


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("kitchen_appliance", ReceiptCategory.KITCHEN_APPLIANCE),
        ("주방 가전", ReceiptCategory.KITCHEN_APPLIANCE),
        ("주방가전", ReceiptCategory.KITCHEN_APPLIANCE),
        ("세탁/청소", ReceiptCategory.LAUNDRY_CLEANING),
        ("리빙/냉난방", ReceiptCategory.LIVING_CLIMATE),
        ("IT 기기", ReceiptCategory.IT_DEVICE),
        ("IT 제품", ReceiptCategory.IT_DEVICE),
        ("영상/IT 제품", ReceiptCategory.IT_DEVICE),
        ("기타 기기", ReceiptCategory.OTHER_DEVICE),
        ("기타 제품", ReceiptCategory.OTHER_DEVICE),
        ("기타", ReceiptCategory.OTHER_DEVICE),
    ],
)
def test_receipt_category_accepts_canonical_values_and_app_aliases(
    raw_value: str,
    expected: ReceiptCategory,
) -> None:
    assert ReceiptCategory(raw_value) is expected


def test_receipt_category_exposes_stable_korean_api_labels() -> None:
    assert {category.value: category.api_label for category in ReceiptCategory} == {
        "kitchen_appliance": "주방 가전",
        "laundry_cleaning": "세탁/청소",
        "living_climate": "리빙/냉난방",
        "it_device": "IT 기기",
        "other_device": "기타 기기",
    }


def test_receipt_category_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="is not a valid ReceiptCategory"):
        ReceiptCategory("새로운 임의 카테고리")
