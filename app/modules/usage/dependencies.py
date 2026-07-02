from typing import Annotated

from fastapi import Depends

from app.modules.credits.dependencies import GetCreditBalanceQueryUseCaseDep
from app.modules.usage.application.queries.get_usage_snapshot.use_case import (
    GetUsageSnapshotQueryUseCase,
)


async def get_usage_snapshot_query_use_case(
    credit_balance_query_use_case: GetCreditBalanceQueryUseCaseDep,
) -> GetUsageSnapshotQueryUseCase:
    return GetUsageSnapshotQueryUseCase(
        credit_balance_query_use_case=credit_balance_query_use_case,
    )


GetUsageSnapshotQueryUseCaseDep = Annotated[
    GetUsageSnapshotQueryUseCase,
    Depends(get_usage_snapshot_query_use_case),
]
