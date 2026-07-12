from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CreateReceiptCommand:
    user_id: UUID
    item_name: str
    payment_date: date
    brand_name: str | None = None
    serial_number: str | None = None
    payment_location: str | None = None
    total_amount: int | None = None
    period_months: int | None = None
    expires_on: date | None = None
    category: str | None = None
    sub_category: str | None = None
    memo: str | None = None
    requires_physical_receipt: bool = False
    receipt_file_ids: tuple[UUID, ...] | None = None
