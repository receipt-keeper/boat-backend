from abc import ABC, abstractmethod

from app.modules.receipts.domain.model import Receipt


class ReceiptRepository(ABC):
    @abstractmethod
    async def create(self, *, receipt: Receipt) -> Receipt:
        raise NotImplementedError
