from typing import Protocol

from app.modules.receipts.application.queries.get_receipt_activity_for_users.query import (
    GetReceiptActivityForUsersQuery,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.result import (
    ReceiptActivityPage,
)


class ReceiptActivityForUsersReader(Protocol):
    async def get_receipt_activity_for_users(
        self,
        *,
        query: GetReceiptActivityForUsersQuery,
    ) -> ReceiptActivityPage: ...
