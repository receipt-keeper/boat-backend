from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CreateReceiptResult:
    receipt_id: UUID
    item_name: str
    brand_name: str | None
    payment_location: str | None
    payment_date: date
    total_amount: int | None
    period_months: int
    expires_on: date
    category: str | None
    memo: str | None
    requires_physical_receipt: bool
    receipt_file_ids: tuple[UUID, ...]
