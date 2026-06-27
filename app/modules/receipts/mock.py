from datetime import date
from typing import Final
from uuid import UUID

from app.modules.receipts.api.schemas import ReceiptResponse

SAMPLE_RECEIPT_ID: Final = UUID("00000000-0000-0000-0000-000000000301")
SAMPLE_FILE_ID: Final = UUID("00000000-0000-0000-0000-000000000201")
SECOND_SAMPLE_FILE_ID: Final = UUID("00000000-0000-0000-0000-000000000202")


def sample_receipt(
    *,
    receipt_id: UUID = SAMPLE_RECEIPT_ID,
    item_name: str = "삼성 냉장고 875L",
    brand_name: str | None = "삼성",
    payment_location: str | None = "전자랜드",
    payment_date: date = date(2024, 5, 26),
    total_amount: int | None = 5137000,
    period_months: int = 24,
    category: str | None = "주방 가전",
    memo: str | None = "주방 냉장고",
    requires_physical_receipt: bool = True,
    receipt_file_ids: list[UUID] | None = None,
) -> ReceiptResponse:
    return ReceiptResponse(
        receipt_id=receipt_id,
        item_name=item_name,
        brand_name=brand_name,
        payment_location=payment_location,
        payment_date=payment_date,
        total_amount=total_amount,
        period_months=period_months,
        expires_on=date(2026, 5, 26),
        category=category,
        memo=memo,
        requires_physical_receipt=requires_physical_receipt,
        receipt_file_ids=receipt_file_ids or [SAMPLE_FILE_ID],
    )
