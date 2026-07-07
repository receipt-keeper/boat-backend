from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.modules.receipts.api.schemas import ReceiptFileResponse, ReceiptResponse
from app.modules.receipts.domain.service_centers import resolve_service_center_url

SAMPLE_RECEIPT_ID: Final = UUID("00000000-0000-0000-0000-000000000301")
SAMPLE_FILE_ID: Final = UUID("00000000-0000-0000-0000-000000000201")
SECOND_SAMPLE_FILE_ID: Final = UUID("00000000-0000-0000-0000-000000000202")
SAMPLE_IMAGE_URL_LARGE: Final = "https://picsum.photos/id/1060/960/640"
SAMPLE_IMAGE_URL_SQUARE: Final = "https://picsum.photos/id/180/512/512"
SAMPLE_IMAGE_URL_PORTRAIT: Final = "https://picsum.photos/id/160/480/720"


def _sample_receipt_files(file_ids: list[UUID]) -> list[ReceiptFileResponse]:
    return [
        ReceiptFileResponse(
            fileId=file_id,
            contentPath=f"/api/v1/files/{file_id}/content",
        )
        for file_id in file_ids
    ]


SAMPLE_RECEIPTS: Final[tuple[ReceiptResponse, ...]] = (
    ReceiptResponse(
        receiptId=SAMPLE_RECEIPT_ID,
        itemName="삼성 냉장고 875L",
        brandName="삼성",
        paymentLocation="전자랜드",
        paymentDate=date(2024, 5, 26),
        totalAmount=5137000,
        periodMonths=24,
        expiresOn=date(2026, 7, 10),
        category="주방 가전",
        subCategory="냉장고",
        memo="주방 냉장고",
        requiresPhysicalReceipt=True,
        receiptFileIds=[SAMPLE_FILE_ID],
        receiptFiles=_sample_receipt_files([SAMPLE_FILE_ID]),
        imageUrl=SAMPLE_IMAGE_URL_LARGE,
        warrantyDDay=14,
        serialNumber="SN-20240526-001",
        supportUrl=resolve_service_center_url(brand_name="삼성", item_name="삼성 냉장고 875L"),
        registeredAt=datetime(2026, 6, 12, 9, 0),
    ),
    ReceiptResponse(
        receiptId=UUID("00000000-0000-0000-0000-000000000302"),
        itemName="LG 세탁기",
        brandName="LG",
        paymentLocation="하이마트",
        paymentDate=date(2025, 1, 5),
        totalAmount=1290000,
        periodMonths=12,
        expiresOn=date(2026, 6, 20),
        category="세탁/청소",
        subCategory="세탁기",
        memo=None,
        requiresPhysicalReceipt=True,
        receiptFileIds=[SECOND_SAMPLE_FILE_ID],
        receiptFiles=_sample_receipt_files([SECOND_SAMPLE_FILE_ID]),
        imageUrl=SAMPLE_IMAGE_URL_SQUARE,
        warrantyDDay=-6,
        serialNumber=None,
        supportUrl=resolve_service_center_url(brand_name="LG", item_name="LG 세탁기"),
        registeredAt=datetime(2026, 6, 10, 14, 30),
    ),
    ReceiptResponse(
        receiptId=UUID("00000000-0000-0000-0000-000000000303"),
        itemName="다이슨 청소기",
        brandName="Dyson",
        paymentLocation="코스트코",
        paymentDate=date(2026, 3, 2),
        totalAmount=890000,
        periodMonths=24,
        expiresOn=date(2028, 3, 2),
        category="세탁/청소",
        subCategory="청소기",
        memo="거실 청소용",
        requiresPhysicalReceipt=True,
        receiptFileIds=[UUID("00000000-0000-0000-0000-000000000203")],
        receiptFiles=_sample_receipt_files([UUID("00000000-0000-0000-0000-000000000203")]),
        imageUrl=SAMPLE_IMAGE_URL_PORTRAIT,
        warrantyDDay=615,
        serialNumber=None,
        supportUrl=resolve_service_center_url(brand_name="Dyson", item_name="다이슨 청소기"),
        registeredAt=datetime(2026, 6, 8, 11, 15),
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
    sub_category: str | None = "냉장고",
    memo: str | None = "주방 냉장고",
    requires_physical_receipt: bool = True,
    receipt_file_ids: list[UUID] | None = None,
) -> ReceiptResponse:
    receipt_file_ids = receipt_file_ids or [SAMPLE_FILE_ID]
    return ReceiptResponse(
        receiptId=receipt_id,
        itemName=item_name,
        brandName=brand_name,
        paymentLocation=payment_location,
        paymentDate=payment_date,
        totalAmount=total_amount,
        periodMonths=period_months,
        expiresOn=date(2026, 5, 26),
        category=category,
        subCategory=sub_category,
        memo=memo,
        requiresPhysicalReceipt=requires_physical_receipt,
        receiptFileIds=receipt_file_ids,
        receiptFiles=_sample_receipt_files(receipt_file_ids),
        imageUrl=SAMPLE_IMAGE_URL_LARGE,
        warrantyDDay=14,
        serialNumber="SN-20240526-001",
        supportUrl=resolve_service_center_url(brand_name=brand_name, item_name=item_name),
        registeredAt=datetime(2026, 6, 12, 9, 0),
    )


def receipt_with_id(receipt_id: UUID) -> ReceiptResponse:
    for receipt in SAMPLE_RECEIPTS:
        if receipt.receipt_id == receipt_id:
            return receipt
    return SAMPLE_RECEIPTS[0].model_copy(update={"receipt_id": receipt_id})
