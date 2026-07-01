from app.modules.credits.application.queries.get_credit_balance.query import (
    GetCreditBalanceQuery,
)
from app.modules.credits.application.queries.get_credit_balance.use_case import (
    GetCreditBalanceQueryUseCase,
)
from app.modules.usage.application.queries.get_usage_snapshot.query import (
    GetUsageSnapshotQuery,
)
from app.modules.usage.domain import OcrUsage, UsageSnapshot


class GetUsageSnapshotQueryUseCase:
    def __init__(
        self,
        *,
        credit_balance_query_use_case: GetCreditBalanceQueryUseCase,
    ) -> None:
        self._credit_balance_query_use_case = credit_balance_query_use_case

    async def execute(self, query: GetUsageSnapshotQuery) -> UsageSnapshot:
        balance = await self._credit_balance_query_use_case.execute(
            GetCreditBalanceQuery(user_id=query.user_id)
        )
        return UsageSnapshot(
            ocr=OcrUsage(
                remaining_count=balance.remaining_count,
                can_analyze=balance.remaining_count > 0,
            )
        )
