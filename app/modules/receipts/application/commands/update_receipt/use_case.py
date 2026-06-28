from app.core.application.unit_of_work import UnitOfWork
from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.receipts.application.commands.update_receipt.command import (
    UpdateReceiptCommand,
)
from app.modules.receipts.application.ports.receipt_repository import ReceiptRepository
from app.modules.receipts.application.read_models.receipt import ReceiptReadModel
from app.modules.receipts.domain.exceptions import ReceiptNotFoundError
from app.modules.receipts.domain.model import Receipt


class UpdateReceiptCommandUseCase:
    def __init__(self, *, receipt_repository: ReceiptRepository, unit_of_work: UnitOfWork) -> None:
        self._receipt_repository = receipt_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: UpdateReceiptCommand) -> ReceiptReadModel:
        current = await self._receipt_repository.find_by_id_for_user(
            receipt_id=command.receipt_id,
            user_id=command.user_id,
        )
        if current is None:
            raise ReceiptNotFoundError(receipt_id=command.receipt_id)

        receipt = Receipt.create(
            receipt_id=current.receipt_id,
            user_id=command.user_id,
            item_name=_updated_value(command, "item_name", current.item_name),
            brand_name=(
                command.brand_name if _has_update(command, "brand_name") else current.brand_name
            ),
            payment_location=(
                command.payment_location
                if _has_update(command, "payment_location")
                else current.payment_location
            ),
            payment_date=_updated_value(command, "payment_date", current.payment_date),
            total_amount=(
                command.total_amount
                if _has_update(command, "total_amount")
                else current.total_amount
            ),
            period_months=_required_updated_value(
                command,
                "period_months",
                current.period_months,
                "무상 AS 기간",
            ),
            category=command.category if _has_update(command, "category") else current.category,
            memo=command.memo if _has_update(command, "memo") else current.memo,
            requires_physical_receipt=_updated_value(
                command,
                "requires_physical_receipt",
                current.requires_physical_receipt,
            ),
            receipt_file_ids=_updated_value(
                command,
                "receipt_file_ids",
                current.receipt_file_ids,
            ),
        )
        updated = await self._receipt_repository.update(receipt=receipt)
        if updated is None:
            raise ReceiptNotFoundError(receipt_id=command.receipt_id)
        await self._unit_of_work.commit()
        return updated


def _has_update(command: UpdateReceiptCommand, field: str) -> bool:
    return field in command.updated_fields


def _updated_value[T](command: UpdateReceiptCommand, field: str, current_value: T) -> T:
    if not _has_update(command, field):
        return current_value
    return getattr(command, field)


def _required_updated_value[T](
    command: UpdateReceiptCommand,
    field: str,
    current_value: T,
    label: str,
) -> T:
    if not _has_update(command, field):
        return current_value

    updated_value = getattr(command, field)
    if updated_value is None:
        raise ValidationError([ErrorDetail(field=field, message=f"{label}은 필수입니다.")])
    return updated_value
