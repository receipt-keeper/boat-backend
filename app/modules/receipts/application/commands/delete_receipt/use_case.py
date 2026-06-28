from app.core.application.unit_of_work import UnitOfWork
from app.modules.receipts.application.commands.delete_receipt.command import (
    DeleteReceiptCommand,
)
from app.modules.receipts.application.ports.receipt_repository import ReceiptRepository
from app.modules.receipts.domain.exceptions import ReceiptNotFoundError


class DeleteReceiptCommandUseCase:
    def __init__(self, *, receipt_repository: ReceiptRepository, unit_of_work: UnitOfWork) -> None:
        self._receipt_repository = receipt_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: DeleteReceiptCommand) -> None:
        deleted = await self._receipt_repository.delete_by_id_for_user(
            receipt_id=command.receipt_id,
            user_id=command.user_id,
        )
        if not deleted:
            raise ReceiptNotFoundError(receipt_id=command.receipt_id)
        await self._unit_of_work.commit()
