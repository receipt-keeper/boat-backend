from typing import Protocol

from app.core.application.unit_of_work import UnitOfWork
from app.modules.credits.application.commands.use_credit.command import UseCreditCommand
from app.modules.credits.domain import CreditAmount, CreditReason
from app.modules.ocr.application.commands.extract_receipt_ocr.command import (
    ExtractReceiptOcrCommand,
)
from app.modules.ocr.application.ports.receipt_ocr_client import ReceiptOcrClientPort
from app.modules.ocr.domain.exceptions import ReceiptImageUnreadableError
from app.modules.ocr.domain.model import ReceiptOcrResult


class UseCreditCommandExecutor(Protocol):
    async def execute(self, command: UseCreditCommand) -> None: ...


class ExtractReceiptOcrCommandUseCase:
    def __init__(
        self,
        *,
        ocr_client: ReceiptOcrClientPort,
        reserve_credit_command_use_case: UseCreditCommandExecutor,
        finalize_credit_usage_command_use_case: UseCreditCommandExecutor,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._ocr_client = ocr_client
        self._reserve_credit_command_use_case = reserve_credit_command_use_case
        self._finalize_credit_usage_command_use_case = finalize_credit_usage_command_use_case
        self._unit_of_work = unit_of_work

    async def execute(self, command: ExtractReceiptOcrCommand) -> ReceiptOcrResult:
        ocr_credit_amount = CreditAmount(value=1, field_name="amount")
        use_credit_command = UseCreditCommand(
            user_id=command.user_id,
            amount=ocr_credit_amount,
            reason=CreditReason.OCR_USAGE,
        )
        await self._reserve_credit_command_use_case.execute(use_credit_command)
        try:
            extracted = await self._ocr_client.extract(images=command.images)
            if extracted.unreadable_file_indexes:
                raise ReceiptImageUnreadableError(
                    file_indexes=extracted.unreadable_file_indexes,
                )
            if not (extracted.item_name or "").strip():
                raise ReceiptImageUnreadableError(
                    file_indexes=tuple(image.file_index for image in command.images),
                )

            result = ReceiptOcrResult.create(
                item_name=extracted.item_name,
                brand_name=extracted.brand_name,
                serial_number=extracted.serial_number,
                payment_location=extracted.payment_location,
                payment_date=extracted.payment_date,
                total_amount=extracted.total_amount,
                period_months=extracted.period_months,
                category=extracted.category,
                sub_category=extracted.sub_category,
            )
            await self._finalize_credit_usage_command_use_case.execute(use_credit_command)
            return result
        except Exception:
            await self._unit_of_work.rollback()
            raise
