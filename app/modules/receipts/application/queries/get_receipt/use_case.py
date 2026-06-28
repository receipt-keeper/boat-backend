from app.modules.receipts.application.ports.receipt_repository import ReceiptRepository
from app.modules.receipts.application.queries.get_receipt.query import GetReceiptQuery
from app.modules.receipts.application.read_models.receipt import ReceiptReadModel
from app.modules.receipts.domain.exceptions import ReceiptNotFoundError


class GetReceiptQueryUseCase:
    def __init__(self, *, receipt_repository: ReceiptRepository) -> None:
        self._receipt_repository = receipt_repository

    async def execute(self, query: GetReceiptQuery) -> ReceiptReadModel:
        receipt = await self._receipt_repository.find_by_id_for_user(
            receipt_id=query.receipt_id,
            user_id=query.user_id,
        )
        if receipt is None:
            raise ReceiptNotFoundError(receipt_id=query.receipt_id)
        return receipt
