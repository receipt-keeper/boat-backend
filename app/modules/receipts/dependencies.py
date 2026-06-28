from typing import Annotated

from fastapi import Depends

from app.core.application.unit_of_work import UnitOfWork
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.receipts.application.commands.create_receipt.use_case import (
    CreateReceiptCommandUseCase,
)
from app.modules.receipts.application.commands.delete_receipt.use_case import (
    DeleteReceiptCommandUseCase,
)
from app.modules.receipts.application.commands.update_receipt.use_case import (
    UpdateReceiptCommandUseCase,
)
from app.modules.receipts.application.ports.receipt_repository import ReceiptRepository
from app.modules.receipts.application.queries.get_receipt.use_case import (
    GetReceiptQueryUseCase,
)
from app.modules.receipts.application.queries.list_receipts.use_case import (
    ListReceiptsQueryUseCase,
)
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


async def get_list_receipts_query_use_case(
    receipt_repository: Annotated[ReceiptRepository, Depends(get_receipt_repository)],
) -> ListReceiptsQueryUseCase:
    return ListReceiptsQueryUseCase(receipt_repository=receipt_repository)


async def get_get_receipt_query_use_case(
    receipt_repository: Annotated[ReceiptRepository, Depends(get_receipt_repository)],
) -> GetReceiptQueryUseCase:
    return GetReceiptQueryUseCase(receipt_repository=receipt_repository)


async def get_update_receipt_command_use_case(
    receipt_repository: Annotated[ReceiptRepository, Depends(get_receipt_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> UpdateReceiptCommandUseCase:
    return UpdateReceiptCommandUseCase(
        receipt_repository=receipt_repository,
        unit_of_work=unit_of_work,
    )


async def get_delete_receipt_command_use_case(
    receipt_repository: Annotated[ReceiptRepository, Depends(get_receipt_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> DeleteReceiptCommandUseCase:
    return DeleteReceiptCommandUseCase(
        receipt_repository=receipt_repository,
        unit_of_work=unit_of_work,
    )


CreateReceiptCommandUseCaseDep = Annotated[
    CreateReceiptCommandUseCase,
    Depends(get_create_receipt_command_use_case),
]
ListReceiptsQueryUseCaseDep = Annotated[
    ListReceiptsQueryUseCase,
    Depends(get_list_receipts_query_use_case),
]
GetReceiptQueryUseCaseDep = Annotated[
    GetReceiptQueryUseCase,
    Depends(get_get_receipt_query_use_case),
]
UpdateReceiptCommandUseCaseDep = Annotated[
    UpdateReceiptCommandUseCase,
    Depends(get_update_receipt_command_use_case),
]
DeleteReceiptCommandUseCaseDep = Annotated[
    DeleteReceiptCommandUseCase,
    Depends(get_delete_receipt_command_use_case),
]
