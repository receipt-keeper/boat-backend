from typing import Annotated

from fastapi import Depends

from app.core.application.unit_of_work import UnitOfWork
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.receipts.application.commands.create_receipt.use_case import (
    CreateReceiptCommandUseCase,
)
from app.modules.receipts.application.ports.receipt_repository import ReceiptRepository
from app.modules.receipts.infrastructure.persistence.repository import SqlAlchemyReceiptRepository


async def get_receipt_repository(session: AsyncSessionDep) -> ReceiptRepository:
    return SqlAlchemyReceiptRepository(session)


async def get_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


async def get_create_receipt_command_use_case(
    receipt_repository: Annotated[ReceiptRepository, Depends(get_receipt_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> CreateReceiptCommandUseCase:
    return CreateReceiptCommandUseCase(
        receipt_repository=receipt_repository,
        unit_of_work=unit_of_work,
    )


CreateReceiptCommandUseCaseDep = Annotated[
    CreateReceiptCommandUseCase,
    Depends(get_create_receipt_command_use_case),
]
