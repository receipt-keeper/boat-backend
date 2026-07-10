from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ReceiptActivity:
    user_id: UUID
    last_receipt_created_at: datetime | None
    receipt_count: int
    cursor_user_id: UUID


@dataclass(frozen=True, slots=True)
class ReceiptActivityPage:
    activities: tuple[ReceiptActivity, ...]
    next_cursor_user_id: UUID | None
    has_next: bool
    limit: int
