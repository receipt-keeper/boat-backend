from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UpdateReceiptCommand:
    user_id: UUID
    receipt_id: UUID
    updated_fields: frozenset[str]
    item_name: str | None = None
    brand_name: str | None = None
    serial_number: str | None = None
    payment_location: str | None = None
    payment_date: date | None = None
    total_amount: int | None = None
    period_months: int | None = None
    category: str | None = None
    sub_category: str | None = None
    memo: str | None = None
    requires_physical_receipt: bool | None = None
    receipt_file_ids: tuple[UUID, ...] | None = None
