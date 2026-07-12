from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.modules.receipts.domain.value_objects import ReceiptCategory


@dataclass(frozen=True, slots=True)
class CreateReceiptResult:
    receipt_id: UUID
    item_name: str
    brand_name: str | None
    serial_number: str | None
    payment_location: str | None
    payment_date: date
    total_amount: int | None
    period_months: int
    expires_on: date
    category: ReceiptCategory | None
    sub_category: str | None
    memo: str | None
    requires_physical_receipt: bool
    receipt_file_ids: tuple[UUID, ...]
    registered_at: datetime
