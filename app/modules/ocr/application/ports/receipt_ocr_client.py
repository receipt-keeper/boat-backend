from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ReceiptOcrImage:
    file_index: int
    content: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class ExtractedReceiptOcrFields:
    item_name: str | None
    brand_name: str | None
    serial_number: str | None
    payment_location: str | None
    payment_date: date | None
    total_amount: int | None
    period_months: int | None
    category: str | None
    sub_category: str | None
    expires_on: date | None = None
    unreadable_file_indexes: tuple[int, ...] = ()


class ReceiptOcrClientPort(Protocol):
    async def extract(
        self,
        *,
        images: tuple[ReceiptOcrImage, ...],
    ) -> ExtractedReceiptOcrFields: ...
