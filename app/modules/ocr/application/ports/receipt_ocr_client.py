from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExtractedReceiptOcrFields:
    item_name: str
    brand_name: str | None
    payment_location: str | None
    payment_date: date | None
    total_amount: int | None
    period_months: int | None
    category: str | None
    sub_category: str | None


class ReceiptOcrClientPort(Protocol):
    async def extract(
        self,
        *,
        image_content: bytes,
        content_type: str,
    ) -> ExtractedReceiptOcrFields: ...
