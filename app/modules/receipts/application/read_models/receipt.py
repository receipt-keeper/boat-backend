from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.modules.receipts.domain.model import warranty_d_day, warranty_status
from app.modules.receipts.domain.value_objects import ReceiptStatusFilter


@dataclass(frozen=True, slots=True)
class ReceiptReadModel:
    receipt_id: UUID
    user_id: UUID
    item_name: str
    brand_name: str | None
    serial_number: str | None
    payment_location: str | None
    payment_date: date
    total_amount: int | None
    period_months: int
    expires_on: date
    category: str | None
    sub_category: str | None
    memo: str | None
    requires_physical_receipt: bool
    receipt_file_ids: tuple[UUID, ...]
    registered_at: datetime

    @property
    def warranty_d_day(self) -> int:
        return warranty_d_day(self.expires_on)

    @property
    def warranty_status(self) -> ReceiptStatusFilter:
        return warranty_status(self.expires_on)
