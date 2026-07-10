from app.modules.receipts.application.queries.list_receipts_expiring_on.port import (
    ReceiptsExpiringOnReader,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.query import (
    ListReceiptsExpiringOnQuery,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.result import (
    ExpiringReceiptsPage,
)


class ListReceiptsExpiringOnQueryUseCase:
    def __init__(self, *, reader: ReceiptsExpiringOnReader) -> None:
        self._reader = reader

    async def execute(self, query: ListReceiptsExpiringOnQuery) -> ExpiringReceiptsPage:
        return await self._reader.list_receipts_expiring_on(query=query)
