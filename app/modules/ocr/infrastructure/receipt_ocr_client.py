from __future__ import annotations

import base64
from datetime import date
from enum import StrEnum
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.modules.ocr.application.ports.receipt_ocr_client import (
    ExtractedReceiptOcrFields,
    ReceiptOcrClientPort,
    ReceiptOcrImage,
    ReceiptTransactionEvidence,
)
from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError
from app.modules.ocr.domain.model import (
    DEFAULT_CATEGORY,
    DEFAULT_SUB_CATEGORY,
    blank_to_none,
)

_RECEIPT_OCR_PROMPT = """
You are an information extraction specialist for receipts.

The input contains one or more images in transmission order.
Classify each image by its overall document purpose before extracting any fields.
At least one image must be an actual purchase receipt for a household appliance, electronic,
or IT device. A supported receipt may be a paper receipt or a digital receipt whose primary
content is a real completed transaction.
Visible device names, brands, prices, dates, or receipt-like UI elements alone are not sufficient
evidence that the overall image is a receipt.
Never treat advertisements, promotional posters, app launch or onboarding screens, UI mockups,
product pages, shopping listings, catalogs, general documents, or ordinary photos as receipts,
even when they contain a well-known electronic product name or an embedded receipt-like screen.
Warranty documents, protection plans, and product labels are supplementary evidence only when
the same request contains at least one actual supported receipt.
Images may show different, consecutive, or overlapping sections of a supported receipt, or
supplementary warranty documents or product labels for the same purchase.
Treat a readable partial section as valid even when it does not contain all receipt fields
by itself.
Treat all readable images as one evidence set and extract one combined receipt result.
A supported receipt requires multiple independent transaction signals across the full image set.
It must visibly contain all of: a merchant, a purchased device line item, and a total paid amount.
It must also contain explicit proof that payment was approved, paid, captured, or completed.
A payment or purchase date and a receipt/order/transaction identifier may support extraction, but
neither proves payment by itself. Product names, dates, and prices in a general document, quotation,
estimate, unpaid order confirmation, or invoice without explicit completed-payment proof,
advertisement, catalog, or product page do not establish a completed purchase.
Return receipt_file_indexes only for images whose overall purpose is an actual supported purchase
receipt. Populate transaction_evidence only for evidence that is visibly present in the images.
If the required evidence set is incomplete, return an empty receipt_file_indexes even if some
receipt-like fields can be extracted.
If the request contains no actual supported receipt, return an empty receipt_file_indexes and put
every readable image index in unsupported_file_indexes, even when electronic-product text appears.
Return unsupported_file_indexes for readable non-receipt images other than the allowed
supplementary evidence described above, and for receipts that are clearly for unsupported general
purchases, including restaurants or food, groceries without a device purchase, transportation,
lodging, medical treatment or pharmacy purchases, clothing, cosmetics, or beauty services.
Do not mark a supported device as unsupported merely because its category is unknown; use
category "other_device" and sub_category "기타" instead.
Return unreadable_file_indexes only for images that are unreadable, corrupted, or cannot be
classified from the visible evidence. A readable advertisement, screenshot, or general document
belongs in unsupported_file_indexes, not unreadable_file_indexes.
The indexes are zero-based and match the IMAGE_INDEX labels in the input.
Extract only information that is clearly supported by the input images.
Do not guess missing or ambiguous values.
If a field other than category or sub_category is not visible or uncertain, return null.
Suggest category and sub_category only from the configured schema descriptions.
If a product does not fit a listed primary category, use category "other_device".
If a product does not fit a listed sub-category, use sub_category "기타".
For protection plans or warranty documents such as AppleCare, classify category and
sub_category by the covered device, not by the protection service itself.
Normalize dates to YYYY-MM-DD when clearly readable.
Extract expires_on only when the document clearly states a coverage, warranty, or
protection expiration/end date. Do not calculate or guess expires_on.
Normalize total_amount as an integer number only when clearly readable.
Extract serial_number from any input image only when it is explicitly identified as a serial
number, such as "Serial Number", "Serial No.", "S/N", or "제조번호".
Do not use an order number, receipt number, product code, or model name as serial_number unless
the image explicitly identifies it as the product serial number.
Respond only with the configured structured output.
Write text values in Korean when applicable.
"""
_HTTP_TIMEOUT_SECONDS = 10.0
_OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


class OcrReceiptCategory(StrEnum):
    KITCHEN_APPLIANCE = "kitchen_appliance"
    LAUNDRY_CLEANING = "laundry_cleaning"
    LIVING_CLIMATE = "living_climate"
    IT_DEVICE = "it_device"
    OTHER_DEVICE = "other_device"

    @property
    def api_label(self) -> str:
        return {
            OcrReceiptCategory.KITCHEN_APPLIANCE: "주방 가전",
            OcrReceiptCategory.LAUNDRY_CLEANING: "세탁/청소",
            OcrReceiptCategory.LIVING_CLIMATE: "리빙/냉난방",
            OcrReceiptCategory.IT_DEVICE: "IT 기기",
            OcrReceiptCategory.OTHER_DEVICE: "기타 기기",
        }[self]


SubCategoryLiteral = Literal[
    "냉장고",
    "전자레인지",
    "밥솥",
    "정수기",
    "세탁기",
    "건조기",
    "청소기",
    "로봇청소기",
    "에어컨",
    "선풍기",
    "공기청정기",
    "가습기",
    "오븐",
    "데스크탑/TV",
    "게임기",
    "카메라",
    "스피커",
    "무선이어폰",
    "노트북",
    "헤드셋",
    "스마트워치",
    "핸드폰",
    "기타",
]


class ReceiptTransactionEvidenceOutput(BaseModel):
    merchant: bool = Field(
        default=False,
        description="A merchant, seller, store, or payment recipient is visibly identified.",
    )
    purchased_item: bool = Field(
        default=False,
        description=(
            "A purchased household appliance, electronic, or IT device line item is visible."
        ),
    )
    total_paid: bool = Field(
        default=False,
        description="A final total paid amount is visibly identified, not merely a listed price.",
    )
    payment_proof: bool = Field(
        default=False,
        description=(
            "Explicit proof that payment was approved, paid, captured, or completed is visible. "
            "A date, order/receipt/transaction identifier, invoice, quotation, or amount alone "
            "is not payment proof."
        ),
    )


class ReceiptOcrStructuredOutput(BaseModel):
    item_name: str | None = Field(
        default=None,
        description=(
            "The appliance, electronic, or IT device being purchased or repaired. "
            "Return null when it is not clearly identifiable."
        ),
    )
    brand_name: str | None = Field(
        default=None,
        description=(
            "The manufacturer or brand name. Return null when it is not shown in the input."
        ),
    )
    serial_number: str | None = Field(
        default=None,
        description=(
            "The product serial number explicitly labeled as Serial Number, Serial No., S/N, "
            "or the Korean label 제조번호 in any input image. Do not confuse it with an order "
            "number, receipt number, product code, or model name. Return null when uncertain."
        ),
    )
    payment_location: str | None = Field(
        default=None,
        description=(
            "The merchant, payment recipient, store, or online marketplace name. "
            "Return null when it is not clearly identifiable."
        ),
    )
    payment_date: date | None = Field(
        default=None,
        description=(
            "The purchase or payment date. Return it only when it can be normalized to YYYY-MM-DD."
        ),
    )
    total_amount: int | None = Field(
        default=None,
        description=(
            "The total paid amount as an integer. Return it only when clearly readable and "
            "remove currency symbols and thousands separators."
        ),
    )
    period_months: int | None = Field(
        default=None,
        description=(
            "The free service or warranty period in months. Return null when the period is not "
            "clearly stated."
        ),
    )
    expires_on: date | None = Field(
        default=None,
        description=(
            "The coverage, protection, or warranty expiration date explicitly stated in the "
            "document. Return it only when it can be normalized to YYYY-MM-DD. Do not calculate "
            "or guess this value."
        ),
    )
    category: OcrReceiptCategory | None = Field(
        default=None,
        description=(
            "The primary category suggestion. Use exactly one of kitchen_appliance, "
            "laundry_cleaning, living_climate, it_device, or other_device. Classify protection "
            "plans by the covered device and use other_device when no category clearly matches."
        ),
    )
    sub_category: SubCategoryLiteral | None = Field(
        default=None,
        description=(
            "The representative device sub-category suggestion. Allowed values are grouped as "
            "follows: kitchen_appliance uses 냉장고, 전자레인지, 밥솥, 정수기, 오븐; "
            "laundry_cleaning uses 세탁기, 건조기, 청소기, 로봇청소기; living_climate uses "
            "에어컨, 선풍기, 공기청정기, 가습기; it_device uses 데스크탑/TV, 스피커, 카메라, "
            "게임기, 헤드셋, 스마트워치, 핸드폰, 무선이어폰, 노트북. Use 기타 when no "
            "listed device clearly matches."
        ),
    )
    transaction_evidence: ReceiptTransactionEvidenceOutput = Field(
        default_factory=ReceiptTransactionEvidenceOutput,
        description=(
            "Visible evidence used to verify that the image set represents a completed purchase. "
            "Set each flag independently and never infer a missing signal from other fields."
        ),
    )
    receipt_file_indexes: list[int] = Field(
        default_factory=list,
        description=(
            "The zero-based IMAGE_INDEX values whose overall document purpose is an actual paper "
            "or digital purchase receipt for a household appliance, electronic, or IT device. "
            "The receipt must present a real completed transaction; a device name, price, date, "
            "advertisement, product page, app screen, UI mockup, warranty document, product label, "
            "or embedded receipt-like content alone is not enough. Return an empty list when no "
            "actual supported receipt is present."
        ),
    )
    unreadable_file_indexes: list[int] = Field(
        default_factory=list,
        description=(
            "The zero-based IMAGE_INDEX values for images that are unreadable, corrupted, or "
            "cannot be classified from the visible evidence. Do not include readable receipts, "
            "relevant warranty documents, or product labels."
        ),
    )
    unsupported_file_indexes: list[int] = Field(
        default_factory=list,
        description=(
            "The zero-based IMAGE_INDEX values for readable images whose overall purpose is not "
            "supported evidence. Include non-electronic receipts and non-receipt images such as "
            "food, restaurants, transportation, lodging, medical or pharmacy, clothing, "
            "cosmetics, beauty services, advertisements, promotional posters, app screens, "
            "UI mockups, product pages, shopping listings, catalogs, general documents, and "
            "ordinary photos. Do not include a warranty document, protection plan, or product "
            "label when the same request contains an actual supported receipt for that purchase. "
            "If no actual supported receipt exists, include every readable image. Do not reject "
            "an actual receipt merely because the device brand or model is unfamiliar; use "
            "category other_device and sub_category 기타 for that case."
        ),
    )

    def to_extracted_fields(self, *, image_count: int) -> ExtractedReceiptOcrFields:
        receipt_file_indexes = set(self.receipt_file_indexes)
        unreadable_file_indexes = set(self.unreadable_file_indexes)
        unsupported_file_indexes = set(self.unsupported_file_indexes)
        all_classified_indexes = (
            receipt_file_indexes | unreadable_file_indexes | unsupported_file_indexes
        )
        if any(index < 0 or index >= image_count for index in all_classified_indexes):
            raise ValueError("OCR provider가 요청 범위를 벗어난 이미지 인덱스를 반환했습니다.")
        if unreadable_file_indexes & unsupported_file_indexes:
            raise ValueError("OCR provider가 동일한 이미지를 두 실패 유형으로 반환했습니다.")
        if receipt_file_indexes & (unreadable_file_indexes | unsupported_file_indexes):
            raise ValueError(
                "OCR provider가 동일한 이미지를 지원 영수증과 실패 유형으로 반환했습니다."
            )
        transaction_evidence = ReceiptTransactionEvidence(
            merchant=self.transaction_evidence.merchant,
            purchased_item=self.transaction_evidence.purchased_item,
            total_paid=self.transaction_evidence.total_paid,
            payment_proof=self.transaction_evidence.payment_proof,
        )

        return ExtractedReceiptOcrFields(
            item_name=blank_to_none(self.item_name),
            brand_name=blank_to_none(self.brand_name),
            serial_number=blank_to_none(self.serial_number),
            payment_location=blank_to_none(self.payment_location),
            payment_date=self.payment_date,
            total_amount=self.total_amount,
            period_months=self.period_months,
            expires_on=self.expires_on,
            category=(self.category.api_label if self.category is not None else DEFAULT_CATEGORY),
            sub_category=blank_to_none(self.sub_category) or DEFAULT_SUB_CATEGORY,
            transaction_evidence=transaction_evidence,
            receipt_file_indexes=tuple(sorted(receipt_file_indexes)),
            unreadable_file_indexes=tuple(sorted(unreadable_file_indexes)),
            unsupported_file_indexes=tuple(sorted(unsupported_file_indexes)),
        )


class ReceiptOcrClient(ReceiptOcrClientPort):
    """계약 확인용 OCR client.

    실제 AI OCR 연동 전까지 Swagger와 앱 연동 흐름을 먼저 맞추기 위한 구현이다.
    """

    async def extract(
        self,
        *,
        images: tuple[ReceiptOcrImage, ...],
    ) -> ExtractedReceiptOcrFields:
        if not images:
            raise ValueError("OCR 분석 이미지가 최소 1개 필요합니다.")

        structured_output = ReceiptOcrStructuredOutput(
            item_name="삼성 냉장고 875L",
            brand_name="삼성",
            serial_number="SN-20240526-001",
            payment_location="테스트 구매처",
            payment_date=date.today(),
            total_amount=129000,
            period_months=None,
            expires_on=None,
            category=OcrReceiptCategory.KITCHEN_APPLIANCE,
            sub_category="냉장고",
            transaction_evidence=ReceiptTransactionEvidenceOutput(
                merchant=True,
                purchased_item=True,
                total_paid=True,
                payment_proof=True,
            ),
            receipt_file_indexes=[0],
        )
        return structured_output.to_extracted_fields(image_count=len(images))


class OpenRouterReceiptOcrClient(ReceiptOcrClientPort):
    def __init__(self, *, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def extract(
        self,
        *,
        images: tuple[ReceiptOcrImage, ...],
    ) -> ExtractedReceiptOcrFields:
        try:
            if not images:
                raise ValueError("OCR 분석 이미지가 최소 1개 필요합니다.")

            multimodal_content = _build_openrouter_multimodal_content(images=images)

            payload = {
                "model": self._model,
                "messages": [
                    {
                        "role": "user",
                        "content": multimodal_content,
                    }
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "receipt_ocr_result",
                        "strict": True,
                        "schema": ReceiptOcrStructuredOutput.model_json_schema(),
                    },
                },
            }
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    _OPENROUTER_CHAT_COMPLETIONS_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()

            content = response.json()["choices"][0]["message"]["content"]
            structured_output = ReceiptOcrStructuredOutput.model_validate_json(content)
            return structured_output.to_extracted_fields(image_count=len(images))
        except (
            ValueError,
            OSError,
            KeyError,
            IndexError,
            TypeError,
            httpx.HTTPError,
            PydanticValidationError,
        ) as exception:
            raise ReceiptOcrProviderUnavailableError() from exception


def _build_openrouter_image_url(*, image_content: bytes, content_type: str) -> str:
    encoded_image = base64.b64encode(image_content).decode("ascii")
    return f"data:{content_type};base64,{encoded_image}"


def _build_openrouter_multimodal_content(
    *,
    images: tuple[ReceiptOcrImage, ...],
) -> list[dict[str, object]]:
    content: list[dict[str, object]] = [{"type": "text", "text": _RECEIPT_OCR_PROMPT}]
    for image in images:
        image_url = _build_openrouter_image_url(
            image_content=image.content,
            content_type=image.content_type,
        )
        content.extend(
            [
                {"type": "text", "text": f"IMAGE_INDEX: {image.file_index}"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
        )
    return content
