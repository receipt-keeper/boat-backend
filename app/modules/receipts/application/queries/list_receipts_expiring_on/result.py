from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExpiringReceipt:
    user_id: UUID
    receipt_id: UUID
    item_name: str
    sub_category: str | None
    expires_on: date
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ExpiringReceiptsPage:
    receipts: tuple[ExpiringReceipt, ...]
    next_cursor_receipt_id: UUID | None
    has_next: bool
    limit: int
