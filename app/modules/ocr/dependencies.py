from typing import Annotated

from fastapi import Depends

from app.core.application.unit_of_work import UnitOfWork
from app.core.config.settings import Settings, get_settings
from app.modules.credits.dependencies import (
    FinalizeCreditUsageCommandUseCaseDep,
    ReserveCreditCommandUseCaseDep,
    get_unit_of_work,
)
from app.modules.ocr.application.commands.extract_receipt_ocr.use_case import (
    ExtractReceiptOcrCommandUseCase,
)
from app.modules.ocr.application.ports.receipt_ocr_client import ReceiptOcrClientPort
from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError
from app.modules.ocr.infrastructure.receipt_ocr_client import (
    OpenRouterReceiptOcrClient,
    ReceiptOcrClient,
)


async def get_receipt_ocr_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReceiptOcrClientPort:
    if settings.openrouter_api_key:
        return OpenRouterReceiptOcrClient(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
        )

    if settings.app_env not in {"local", "test"}:
        raise ReceiptOcrProviderUnavailableError()

    return ReceiptOcrClient()


async def get_extract_receipt_ocr_command_use_case(
    ocr_client: Annotated[
        ReceiptOcrClientPort,
        Depends(get_receipt_ocr_client),
    ],
    reserve_credit_command_use_case: ReserveCreditCommandUseCaseDep,
    finalize_credit_usage_command_use_case: FinalizeCreditUsageCommandUseCaseDep,
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> ExtractReceiptOcrCommandUseCase:
    return ExtractReceiptOcrCommandUseCase(
        ocr_client=ocr_client,
        reserve_credit_command_use_case=reserve_credit_command_use_case,
        finalize_credit_usage_command_use_case=finalize_credit_usage_command_use_case,
        unit_of_work=unit_of_work,
    )


ExtractReceiptOcrCommandUseCaseDep = Annotated[
    ExtractReceiptOcrCommandUseCase,
    Depends(get_extract_receipt_ocr_command_use_case),
]
