import logging
from time import perf_counter
from typing import Protocol

from app.core.application.unit_of_work import UnitOfWork
from app.modules.credits.application.commands.use_credit.command import UseCreditCommand
from app.modules.credits.domain import CreditAmount, CreditReason
from app.modules.ocr.application.commands.extract_receipt_ocr.command import (
    ExtractReceiptOcrCommand,
)
from app.modules.ocr.application.ports.receipt_ocr_client import ReceiptOcrClientPort
from app.modules.ocr.domain.exceptions import (
    ReceiptImageUnreadableError,
    ReceiptOcrProviderUnavailableError,
    UnsupportedReceiptError,
)
from app.modules.ocr.domain.model import ReceiptOcrResult

logger = logging.getLogger(__name__)


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
        started_at = perf_counter()
        ocr_credit_amount = CreditAmount(value=1, field_name="amount")
        use_credit_command = UseCreditCommand(
            user_id=command.user_id,
            amount=ocr_credit_amount,
            reason=CreditReason.OCR_USAGE,
        )
        await self._reserve_credit_command_use_case.execute(use_credit_command)
        try:
            extracted = await self._ocr_client.extract(images=command.images)
            if extracted.unsupported_file_indexes:
                raise UnsupportedReceiptError(
                    file_indexes=extracted.unsupported_file_indexes,
                )
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
                expires_on=extracted.expires_on,
                category=extracted.category,
                sub_category=extracted.sub_category,
            )
            await self._finalize_credit_usage_command_use_case.execute(use_credit_command)
            logger.info(
                "ocr_analysis_succeeded user_id=%s image_count=%d content_types=%s "
                "sizes=%s elapsed_ms=%d",
                command.user_id,
                len(command.images),
                tuple(image.content_type for image in command.images),
                tuple(len(image.content) for image in command.images),
                _elapsed_ms(started_at),
            )
            return result
        except UnsupportedReceiptError as exception:
            await self._unit_of_work.rollback()
            _log_ocr_failure(
                command=command,
                reason="unsupported_receipt",
                exception=exception,
                file_indexes=exception.file_indexes,
                started_at=started_at,
            )
            raise
        except ReceiptImageUnreadableError as exception:
            await self._unit_of_work.rollback()
            _log_ocr_failure(
                command=command,
                reason="unreadable_image",
                exception=exception,
                file_indexes=exception.file_indexes,
                started_at=started_at,
            )
            raise
        except ReceiptOcrProviderUnavailableError as exception:
            await self._unit_of_work.rollback()
            _log_ocr_failure(
                command=command,
                reason="provider_unavailable",
                exception=exception,
                file_indexes=(),
                started_at=started_at,
            )
            raise
        except Exception as exception:
            await self._unit_of_work.rollback()
            _log_ocr_failure(
                command=command,
                reason="unexpected",
                exception=exception,
                file_indexes=(),
                started_at=started_at,
            )
            raise


def _log_ocr_failure(
    *,
    command: ExtractReceiptOcrCommand,
    reason: str,
    exception: Exception,
    file_indexes: tuple[int, ...],
    started_at: float,
) -> None:
    root_exception = exception.__cause__ or exception
    logger.warning(
        "ocr_analysis_failed reason=%s user_id=%s image_count=%d content_types=%s "
        "sizes=%s file_indexes=%s exception_type=%s elapsed_ms=%d",
        reason,
        command.user_id,
        len(command.images),
        tuple(image.content_type for image in command.images),
        tuple(len(image.content) for image in command.images),
        file_indexes,
        type(root_exception).__name__,
        _elapsed_ms(started_at),
    )


def _elapsed_ms(started_at: float) -> int:
    return round((perf_counter() - started_at) * 1000)
