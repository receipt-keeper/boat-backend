from typing import Protocol

from app.modules.receipts.application.queries.list_receipts_expiring_on.query import (
    ListReceiptsExpiringOnQuery,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.result import (
    ExpiringReceiptsPage,
)


class ReceiptsExpiringOnReader(Protocol):
    async def list_receipts_expiring_on(
        self,
        *,
        query: ListReceiptsExpiringOnQuery,
    ) -> ExpiringReceiptsPage: ...
