from app.core.application.unit_of_work import UnitOfWork
from app.modules.receipts.application.commands.create_receipt.command import CreateReceiptCommand
from app.modules.receipts.application.commands.create_receipt.result import CreateReceiptResult
from app.modules.receipts.application.ports.receipt_repository import ReceiptRepository
from app.modules.receipts.domain.model import Receipt


class CreateReceiptCommandUseCase:
    def __init__(self, *, receipt_repository: ReceiptRepository, unit_of_work: UnitOfWork) -> None:
        self._receipt_repository = receipt_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: CreateReceiptCommand) -> CreateReceiptResult:
        receipt = Receipt.create(
            user_id=command.user_id,
            item_name=command.item_name,
            brand_name=command.brand_name,
            serial_number=command.serial_number,
            payment_location=command.payment_location,
            payment_date=command.payment_date,
            total_amount=command.total_amount,
            period_months=command.period_months,
            expires_on=command.expires_on,
            category=command.category,
            sub_category=command.sub_category,
            memo=command.memo,
            requires_physical_receipt=command.requires_physical_receipt,
            receipt_file_ids=command.receipt_file_ids,
        )
        saved = await self._receipt_repository.create(receipt=receipt)
        await self._unit_of_work.commit()
        return CreateReceiptResult(
            receipt_id=saved.receipt_id,
            item_name=saved.item_name,
            brand_name=saved.brand_name,
            serial_number=saved.serial_number,
            payment_location=saved.payment_location,
            payment_date=saved.payment_date,
            total_amount=saved.total_amount,
            period_months=saved.period_months,
            expires_on=saved.expires_on,
            category=saved.category,
            sub_category=saved.sub_category,
            memo=saved.memo,
            requires_physical_receipt=saved.requires_physical_receipt,
            receipt_file_ids=saved.receipt_file_ids,
            registered_at=saved.registered_at,
        )
