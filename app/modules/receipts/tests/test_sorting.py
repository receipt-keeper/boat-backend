from app.modules.receipts.api.router import _sort_receipts
from app.modules.receipts.domain.value_objects import ReceiptSort
from app.modules.receipts.mock import SAMPLE_RECEIPTS


def test_recent_receipt_sort_accepts_missing_registration_time() -> None:
    receipt_without_registration_time = SAMPLE_RECEIPTS[0].model_copy(
        update={"registered_at": None}
    )

    sorted_receipts = _sort_receipts(
        [receipt_without_registration_time, SAMPLE_RECEIPTS[1]],
        ReceiptSort.RECENT,
    )

    assert sorted_receipts == [SAMPLE_RECEIPTS[1], receipt_without_registration_time]
