from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.receipts.application.ports.receipt_repository import ReceiptRepository
from app.modules.receipts.domain.model import Receipt
from app.modules.receipts.infrastructure.persistence import mapper


class SqlAlchemyReceiptRepository(ReceiptRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, receipt: Receipt) -> Receipt:
        record = mapper.receipt_to_record(receipt)
        self._session.add(record)
        for file_id in receipt.receipt_file_ids:
            self._session.add(mapper.attachment_to_record(receipt_id=receipt.id, file_id=file_id))
        await self._session.flush()
        return receipt
