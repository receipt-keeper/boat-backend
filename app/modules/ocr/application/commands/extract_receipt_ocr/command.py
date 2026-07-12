from dataclasses import dataclass
from uuid import UUID

from app.modules.ocr.application.ports.receipt_ocr_client import ReceiptOcrImage


@dataclass(frozen=True, slots=True)
class ExtractReceiptOcrCommand:
    user_id: UUID
    images: tuple[ReceiptOcrImage, ...]
