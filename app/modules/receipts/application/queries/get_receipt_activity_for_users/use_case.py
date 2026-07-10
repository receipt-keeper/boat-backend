from app.modules.receipts.application.queries.get_receipt_activity_for_users.port import (
    ReceiptActivityForUsersReader,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.query import (
    GetReceiptActivityForUsersQuery,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.result import (
    ReceiptActivityPage,
)


class GetReceiptActivityForUsersQueryUseCase:
    def __init__(self, *, reader: ReceiptActivityForUsersReader) -> None:
        self._reader = reader

    async def execute(self, query: GetReceiptActivityForUsersQuery) -> ReceiptActivityPage:
        return await self._reader.get_receipt_activity_for_users(query=query)
