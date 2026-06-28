from dataclasses import dataclass
from uuid import UUID

from app.modules.receipts.domain.value_objects import ReceiptSort, ReceiptStatusFilter


@dataclass(frozen=True, slots=True)
class ListReceiptsQuery:
    user_id: UUID
    status: ReceiptStatusFilter = ReceiptStatusFilter.ALL
    sort: ReceiptSort = ReceiptSort.RECENT
    limit: int = 20
    cursor: str | None = None
    category: str | None = None
    q: str | None = None

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("limit는 1 이상이어야 합니다.")
