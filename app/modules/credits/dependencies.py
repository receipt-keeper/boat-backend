from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.unit_of_work import DeferredCommitUnitOfWork, UnitOfWork
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.credits.application.commands.delete_user_credits.use_case import (
    DeleteUserCreditsCommandUseCase,
)
from app.modules.credits.application.commands.finalize_credit_usage.use_case import (
    FinalizeCreditUsageCommandUseCase,
)
from app.modules.credits.application.commands.grant_credit.use_case import (
    GrantCreditCommandUseCase,
)
from app.modules.credits.application.commands.reserve_credit.use_case import (
    ReserveCreditCommandUseCase,
)
from app.modules.credits.application.commands.use_credit.use_case import (
    UseCreditCommandUseCase,
)
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


def build_grant_credit_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> GrantCreditCommandUseCase:
    return GrantCreditCommandUseCase(
        credit_repository=SqlAlchemyCreditRepository(session),
        unit_of_work=unit_of_work,
    )


def build_delete_user_credits_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> DeleteUserCreditsCommandUseCase:
    return DeleteUserCreditsCommandUseCase(
        credit_repository=SqlAlchemyCreditRepository(session),
        unit_of_work=unit_of_work,
    )


async def get_credit_repository(session: AsyncSessionDep) -> CreditRepository:
    return SqlAlchemyCreditRepository(session)


async def get_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


async def get_use_credit_command_use_case(
    credit_repository: Annotated[CreditRepository, Depends(get_credit_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> UseCreditCommandUseCase:
    return UseCreditCommandUseCase(
        credit_repository=credit_repository,
        unit_of_work=unit_of_work,
    )


async def get_reserve_credit_command_use_case(
    credit_repository: Annotated[CreditRepository, Depends(get_credit_repository)],
) -> ReserveCreditCommandUseCase:
    return ReserveCreditCommandUseCase(credit_repository=credit_repository)


async def get_finalize_credit_usage_command_use_case(
    credit_repository: Annotated[CreditRepository, Depends(get_credit_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> FinalizeCreditUsageCommandUseCase:
    return FinalizeCreditUsageCommandUseCase(
        credit_repository=credit_repository,
        unit_of_work=unit_of_work,
    )


async def get_grant_credit_command_use_case(
    credit_repository: Annotated[CreditRepository, Depends(get_credit_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> GrantCreditCommandUseCase:
    return GrantCreditCommandUseCase(
        credit_repository=credit_repository,
        unit_of_work=unit_of_work,
    )


async def get_deferred_grant_credit_command_use_case(
    credit_repository: Annotated[CreditRepository, Depends(get_credit_repository)],
) -> GrantCreditCommandUseCase:
    return GrantCreditCommandUseCase(
        credit_repository=credit_repository,
        unit_of_work=DeferredCommitUnitOfWork(),
    )


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
UseCreditCommandUseCaseDep = Annotated[
    UseCreditCommandUseCase,
    Depends(get_use_credit_command_use_case),
]
ReserveCreditCommandUseCaseDep = Annotated[
    ReserveCreditCommandUseCase,
    Depends(get_reserve_credit_command_use_case),
]
FinalizeCreditUsageCommandUseCaseDep = Annotated[
    FinalizeCreditUsageCommandUseCase,
    Depends(get_finalize_credit_usage_command_use_case),
]
GrantCreditCommandUseCaseDep = Annotated[
    GrantCreditCommandUseCase,
    Depends(get_grant_credit_command_use_case),
]
ListCreditTransactionsQueryUseCaseDep = Annotated[
    ListCreditTransactionsQueryUseCase,
    Depends(get_list_credit_transactions_query_use_case),
]
