from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from app.modules.receipts.application.queries.list_receipts.query import ListReceiptsQuery
from app.modules.receipts.application.read_models.receipt import ReceiptReadModel
from app.modules.receipts.domain.model import Receipt


@dataclass(frozen=True, slots=True)
class ReceiptListPage:
    receipts: tuple[ReceiptReadModel, ...]
    total_count: int
    next_cursor: str | None
    has_next: bool
    limit: int


class ReceiptRepository(ABC):
    @abstractmethod
    async def create(self, *, receipt: Receipt) -> Receipt:
        raise NotImplementedError

    @abstractmethod
    async def list_by_user(self, *, query: ListReceiptsQuery) -> ReceiptListPage:
        raise NotImplementedError

    @abstractmethod
    async def find_by_id_for_user(
        self,
        *,
        receipt_id: UUID,
        user_id: UUID,
    ) -> ReceiptReadModel | None:
        raise NotImplementedError

    @abstractmethod
    async def update(self, *, receipt: Receipt) -> ReceiptReadModel | None:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_id_for_user(self, *, receipt_id: UUID, user_id: UUID) -> bool:
        raise NotImplementedError
