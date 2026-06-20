from typing import Annotated

from fastapi import Depends

from app.core.config.settings import Settings, get_settings
from app.modules.ocr.application.service import ReceiptOcrService
from app.modules.ocr.infrastructure.receipt_ocr_client import (
    GeminiReceiptOcrClient,
    OpenRouterReceiptOcrClient,
    ReceiptOcrClient,
    ReceiptOcrClientProtocol,
)


async def get_receipt_ocr_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReceiptOcrClientProtocol:
    if settings.openrouter_api_key:
        return OpenRouterReceiptOcrClient(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
        )

    if settings.gemini_api_key:
        return GeminiReceiptOcrClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    return ReceiptOcrClient()


async def get_receipt_ocr_service(
    ocr_client: Annotated[
        ReceiptOcrClientProtocol,
        Depends(get_receipt_ocr_client),
    ],
) -> ReceiptOcrService:
    return ReceiptOcrService(ocr_client)


ReceiptOcrServiceDep = Annotated[
    ReceiptOcrService,
    Depends(get_receipt_ocr_service),
]
