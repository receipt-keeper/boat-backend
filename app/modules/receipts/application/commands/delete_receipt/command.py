from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DeleteReceiptCommand:
    user_id: UUID
    receipt_id: UUID
