from __future__ import annotations

import base64
from datetime import date
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.modules.ocr.application.ports.receipt_ocr_client import (
    ExtractedReceiptOcrFields,
    ReceiptOcrClientPort,
    ReceiptOcrImage,
)
from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError
from app.modules.ocr.domain.model import (
    DEFAULT_CATEGORY,
    DEFAULT_SUB_CATEGORY,
    blank_to_none,
)

_RECEIPT_OCR_PROMPT = """
You are an information extraction specialist for receipts.

The input contains one or more images of the same receipt in transmission order.
Images may show different, consecutive, or overlapping sections of that single receipt.
Treat a readable partial section as valid even when it does not contain all receipt fields
by itself.
Extract one combined receipt result from all readable images.
Return unreadable_file_indexes only for images that are unreadable, corrupted, or unrelated
to the receipt.
The indexes are zero-based and match the IMAGE_INDEX labels in the input.
Extract only information that is clearly supported by the receipt images.
Do not guess missing or ambiguous values.
If a field other than category or sub_category is not visible or uncertain, return null.
Suggest category and sub_category only from the configured schema descriptions.
If a product does not fit a listed primary category, use category "기타 기기".
If a product does not fit a listed sub-category, use sub_category "기타".
Normalize dates to YYYY-MM-DD when clearly readable.
Normalize total_amount as an integer number only when clearly readable.
Extract serial_number only when it is clearly visible on the receipt image.
Respond only with the configured structured output.
Write text values in Korean when applicable.
"""
_HTTP_TIMEOUT_SECONDS = 10.0
_OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
CategoryLiteral = Literal["주방 가전", "세탁/청소", "리빙/냉난방", "IT 기기", "기타 기기"]
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
    "태블릿",
    "게임기",
    "카메라",
    "스피커",
    "무선 이어폰",
    "노트북",
    "헤드셋",
    "스마트워치",
    "핸드폰",
    "기타",
]


class ReceiptOcrStructuredOutput(BaseModel):
    item_name: str | None = Field(
        default=None,
        description="구매/진료/수리 대상이 되는 제품명 또는 항목명. 명확하지 않으면 null.",
    )
    brand_name: str | None = Field(
        default=None,
        description="제조사 또는 브랜드명. 영수증에서 확인되지 않으면 null.",
    )
    serial_number: str | None = Field(
        default=None,
        description="제품 시리얼 넘버. 영수증에서 명확히 확인되지 않으면 null.",
    )
    payment_location: str | None = Field(
        default=None,
        description="구매처, 결제처, 병원명, 매장명 또는 온라인몰 이름. 명확하지 않으면 null.",
    )
    payment_date: date | None = Field(
        default=None,
        description="구매일 또는 결제일. YYYY-MM-DD 형식으로 변환 가능할 때만 입력.",
    )
    total_amount: int | None = Field(
        default=None,
        description="총 결제 금액. 숫자로 명확히 확인될 때만 입력하고 통화기호/쉼표는 제거.",
    )
    period_months: int | None = Field(
        default=None,
        description="무상 AS/보증 기간 개월 수. 영수증에서 명확히 확인되지 않으면 null.",
    )
    category: CategoryLiteral | None = Field(
        default=None,
        description=(
            "대분류 카테고리 추천값. 다음 중 하나만 사용: 주방 가전, 세탁/청소, "
            "리빙/냉난방, IT 기기, 기타 기기. 명확히 맞지 않으면 기타 기기."
        ),
    )
    sub_category: SubCategoryLiteral | None = Field(
        default=None,
        description=(
            "소분류 대표 기기명 추천값. 주방 가전: 냉장고, 전자레인지, 밥솥, 정수기. "
            "세탁/청소: 세탁기, 건조기, 청소기, 로봇청소기. "
            "리빙/냉난방: 에어컨, 선풍기, 공기청정기, 가습기. "
            "IT 기기: 태블릿, 게임기, 카메라, 스피커, 무선 이어폰, 노트북, 헤드셋, "
            "스마트워치, 핸드폰. 없거나 불명확하면 기타."
        ),
    )
    unreadable_file_indexes: list[int] = Field(
        default_factory=list,
        description=(
            "읽을 수 없거나 손상되었거나 영수증과 무관한 이미지의 0-based IMAGE_INDEX 목록. "
            "읽을 수 있는 영수증 일부 이미지는 포함하지 않는다."
        ),
    )

    def to_extracted_fields(self, *, image_count: int) -> ExtractedReceiptOcrFields:
        unreadable_file_indexes = tuple(sorted(set(self.unreadable_file_indexes)))
        if any(index < 0 or index >= image_count for index in unreadable_file_indexes):
            raise ValueError("OCR provider가 요청 범위를 벗어난 이미지 인덱스를 반환했습니다.")

        return ExtractedReceiptOcrFields(
            item_name=blank_to_none(self.item_name),
            brand_name=blank_to_none(self.brand_name),
            serial_number=blank_to_none(self.serial_number),
            payment_location=blank_to_none(self.payment_location),
            payment_date=self.payment_date,
            total_amount=self.total_amount,
            period_months=self.period_months,
            category=blank_to_none(self.category) or DEFAULT_CATEGORY,
            sub_category=blank_to_none(self.sub_category) or DEFAULT_SUB_CATEGORY,
            unreadable_file_indexes=unreadable_file_indexes,
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
        structured_output = ReceiptOcrStructuredOutput(
            item_name="삼성 냉장고 875L",
            brand_name="삼성",
            serial_number="SN-20240526-001",
            payment_location="테스트 구매처",
            payment_date=date.today(),
            total_amount=129000,
            period_months=None,
            category="주방 가전",
            sub_category="냉장고",
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
