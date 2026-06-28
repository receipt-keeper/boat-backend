from app.modules.receipts.application.ports.receipt_repository import ReceiptRepository
from app.modules.receipts.application.queries.list_receipts.query import ListReceiptsQuery
from app.modules.receipts.application.queries.list_receipts.result import ListReceiptsResult


class ListReceiptsQueryUseCase:
    def __init__(self, *, receipt_repository: ReceiptRepository) -> None:
        self._receipt_repository = receipt_repository

    async def execute(self, query: ListReceiptsQuery) -> ListReceiptsResult:
        page = await self._receipt_repository.list_by_user(query=query)
        return ListReceiptsResult(
            receipts=page.receipts,
            total_count=page.total_count,
            next_cursor=page.next_cursor,
            has_next=page.has_next,
            limit=page.limit,
        )
