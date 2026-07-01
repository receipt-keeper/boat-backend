from typing import Annotated

from fastapi import Depends

from app.core.db.session import AsyncSessionDep
from app.modules.credits.application.ports.credit_repository import CreditRepository
from app.modules.credits.application.queries.get_credit_balance.use_case import (
    GetCreditBalanceQueryUseCase,
)
from app.modules.credits.application.queries.list_credit_transactions.use_case import (
    ListCreditTransactionsQueryUseCase,
)
from app.modules.credits.infrastructure.persistence.repository import (
    SqlAlchemyCreditRepository,
)


async def get_credit_repository(session: AsyncSessionDep) -> CreditRepository:
    return SqlAlchemyCreditRepository(session)


async def get_credit_balance_query_use_case(
    credit_repository: Annotated[CreditRepository, Depends(get_credit_repository)],
) -> GetCreditBalanceQueryUseCase:
    return GetCreditBalanceQueryUseCase(credit_repository=credit_repository)


async def get_list_credit_transactions_query_use_case(
    credit_repository: Annotated[CreditRepository, Depends(get_credit_repository)],
) -> ListCreditTransactionsQueryUseCase:
    return ListCreditTransactionsQueryUseCase(credit_repository=credit_repository)


GetCreditBalanceQueryUseCaseDep = Annotated[
    GetCreditBalanceQueryUseCase,
    Depends(get_credit_balance_query_use_case),
]
ListCreditTransactionsQueryUseCaseDep = Annotated[
    ListCreditTransactionsQueryUseCase,
    Depends(get_list_credit_transactions_query_use_case),
]
