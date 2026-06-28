from app.modules.ocr.domain.exceptions import ReceiptImageUnreadableError
from app.modules.ocr.domain.model import ReceiptOcrResult
from app.modules.ocr.infrastructure.receipt_ocr_client import ReceiptOcrClientProtocol


class ReceiptOcrService:
    def __init__(self, ocr_client: ReceiptOcrClientProtocol) -> None:
        self._ocr_client = ocr_client

    async def extract_receipt(
        self,
        *,
        image_content: bytes,
        content_type: str,
    ) -> ReceiptOcrResult:
        extracted = await self._ocr_client.extract(
            image_content=image_content,
            content_type=content_type,
        )
        if not extracted.item_name.strip():
            raise ReceiptImageUnreadableError()

        return ReceiptOcrResult.create(
            item_name=extracted.item_name,
            brand_name=extracted.brand_name,
            payment_location=extracted.payment_location,
            payment_date=extracted.payment_date,
            total_amount=extracted.total_amount,
            period_months=extracted.period_months,
            category=extracted.category,
        )
