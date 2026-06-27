from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.modules.receipts.api.schemas import ReceiptResponse

SAMPLE_RECEIPT_ID: Final = UUID("00000000-0000-0000-0000-000000000301")
SAMPLE_FILE_ID: Final = UUID("00000000-0000-0000-0000-000000000201")
SECOND_SAMPLE_FILE_ID: Final = UUID("00000000-0000-0000-0000-000000000202")

SAMPLE_RECEIPTS: Final[tuple[ReceiptResponse, ...]] = (
    ReceiptResponse(
        receipt_id=SAMPLE_RECEIPT_ID,
        item_name="삼성 냉장고 875L",
        brand_name="삼성",
        payment_location="전자랜드",
        payment_date=date(2024, 5, 26),
        total_amount=5137000,
        period_months=24,
        expires_on=date(2026, 7, 10),
        category="주방 가전",
        memo="주방 냉장고",
        requires_physical_receipt=True,
        receipt_file_ids=[SAMPLE_FILE_ID],
        image_url="/api/v1/files/00000000-0000-0000-0000-000000000201/content",
        warranty_d_day=14,
        serial_number="SN-20240526-001",
        support_url="https://www.samsungsvc.co.kr",
        registered_at=datetime(2026, 6, 12, 9, 0),
    ),
    ReceiptResponse(
        receipt_id=UUID("00000000-0000-0000-0000-000000000302"),
        item_name="LG 세탁기",
        brand_name="LG",
        payment_location="하이마트",
        payment_date=date(2025, 1, 5),
        total_amount=1290000,
        period_months=12,
        expires_on=date(2026, 6, 20),
        category="세탁/청소",
        memo=None,
        requires_physical_receipt=True,
        receipt_file_ids=[SECOND_SAMPLE_FILE_ID],
        image_url="/api/v1/files/00000000-0000-0000-0000-000000000202/content",
        warranty_d_day=-6,
        serial_number=None,
        support_url="https://www.lge.co.kr/support",
        registered_at=datetime(2026, 6, 10, 14, 30),
    ),
    ReceiptResponse(
        receipt_id=UUID("00000000-0000-0000-0000-000000000303"),
        item_name="다이슨 청소기",
        brand_name="Dyson",
        payment_location="코스트코",
        payment_date=date(2026, 3, 2),
        total_amount=890000,
        period_months=24,
        expires_on=date(2028, 3, 2),
        category="세탁/청소",
        memo="거실 청소용",
        requires_physical_receipt=True,
        receipt_file_ids=[UUID("00000000-0000-0000-0000-000000000203")],
        image_url="/api/v1/files/00000000-0000-0000-0000-000000000203/content",
        warranty_d_day=615,
        serial_number=None,
        support_url="https://www.dyson.co.kr/support",
        registered_at=datetime(2026, 6, 8, 11, 15),
    ),
)


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
        image_url="/api/v1/files/00000000-0000-0000-0000-000000000201/content",
        warranty_d_day=14,
        serial_number="SN-20240526-001",
        support_url="https://www.samsungsvc.co.kr",
        registered_at=datetime(2026, 6, 12, 9, 0),
    )


def receipt_with_id(receipt_id: UUID) -> ReceiptResponse:
    for receipt in SAMPLE_RECEIPTS:
        if receipt.receipt_id == receipt_id:
            return receipt
    return SAMPLE_RECEIPTS[0].model_copy(update={"receipt_id": receipt_id})
