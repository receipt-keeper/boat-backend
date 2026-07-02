from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ListCreditTransactionsQuery:
    user_id: UUID
    cursor: str | None = None
    limit: int = 20
