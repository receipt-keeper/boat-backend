from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GetReceiptQuery:
    user_id: UUID
    receipt_id: UUID
