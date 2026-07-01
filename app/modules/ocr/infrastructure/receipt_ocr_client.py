from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import httpx
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError

_RECEIPT_OCR_PROMPT = """
You are an information extraction specialist for receipts.

Extract only information that is clearly supported by the receipt image.
Do not guess missing or ambiguous values.
If a field is not visible or uncertain, return null.
Suggest category and sub_category only from the configured schema descriptions.
If a product does not fit a listed sub-category but fits a category, use sub_category "기타".
Normalize dates to YYYY-MM-DD when clearly readable.
Normalize total_amount as an integer number only when clearly readable.
Do not extract serial numbers. Serial number support is out of scope for MVP.
Respond only with the configured structured output.
Write text values in Korean when applicable.
"""
_HTTP_TIMEOUT_SECONDS = 10.0
_OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass(frozen=True)
class ExtractedReceiptOcrFields:
    item_name: str
    brand_name: str | None
    payment_location: str | None
    payment_date: date | None
    total_amount: int | None
    period_months: int | None
    category: str | None
    sub_category: str | None


class ReceiptOcrStructuredOutput(BaseModel):
    item_name: str | None = Field(
        default=None,
        description="구매/진료/수리 대상이 되는 제품명 또는 항목명. 명확하지 않으면 null.",
    )
    brand_name: str | None = Field(
        default=None,
        description="제조사 또는 브랜드명. 영수증에서 확인되지 않으면 null.",
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
    category: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "대분류 카테고리 추천값. 다음 중 하나만 사용: 주방 가전, 세탁/청소, "
            "리빙/냉난방, IT 기기, 기타 기기. 명확하지 않으면 null."
        ),
    )
    sub_category: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "소분류 대표 기기명 추천값. 주방 가전: 냉장고, 전자레인지, 밥솥, 정수기. "
            "세탁/청소: 세탁기, 건조기, 청소기, 로봇청소기. "
            "리빙/냉난방: 에어컨, 선풍기, 공기청정기, 가습기. "
            "IT 기기: 태블릿, 게임기, 카메라, 스피커, 무선 이어폰, 노트북, 헤드셋, "
            "스마트워치, 핸드폰. 없거나 불명확하면 기타."
        ),
    )

    def to_extracted_fields(self) -> ExtractedReceiptOcrFields:
        return ExtractedReceiptOcrFields(
            item_name=(self.item_name or "").strip(),
            brand_name=self.brand_name,
            payment_location=self.payment_location,
            payment_date=self.payment_date,
            total_amount=self.total_amount,
            period_months=self.period_months,
            category=(self.category or "").strip() or None,
            sub_category=(self.sub_category or "").strip() or None,
        )


class ReceiptOcrClientProtocol(Protocol):
    async def extract(
        self,
        *,
        image_content: bytes,
        content_type: str,
    ) -> ExtractedReceiptOcrFields: ...


class ReceiptOcrClient:
    """계약 확인용 OCR client.

    실제 AI OCR 연동 전까지 Swagger와 앱 연동 흐름을 먼저 맞추기 위한 구현이다.
    """

    async def extract(
        self,
        *,
        image_content: bytes,
        content_type: str,
    ) -> ExtractedReceiptOcrFields:
        structured_output = ReceiptOcrStructuredOutput(
            item_name="삼성 냉장고 875L",
            brand_name="삼성",
            payment_location="테스트 구매처",
            payment_date=date.today(),
            total_amount=129000,
            period_months=None,
            category="주방 가전",
            sub_category="냉장고",
        )
        return structured_output.to_extracted_fields()


class OpenRouterReceiptOcrClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def extract(
        self,
        *,
        image_content: bytes,
        content_type: str,
    ) -> ExtractedReceiptOcrFields:
        try:
            image_url = _build_openrouter_image_url(
                image_content=image_content,
                content_type=content_type,
            )
            payload = {
                "model": self._model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _RECEIPT_OCR_PROMPT},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
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
            return structured_output.to_extracted_fields()
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
