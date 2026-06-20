from __future__ import annotations

import asyncio
import base64
import mimetypes
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError

_RECEIPT_OCR_PROMPT = """
You are an OCR extraction engine for Korean receipts.

Extract only the fields defined in the response schema.
Return null for unknown fields.
Do not include raw OCR text.
Do not extract serial numbers. Serial number support is out of scope for MVP.

Field rules:
- item_name: representative purchased item, product, or service name.
  For medical receipts, use values such as "진료비" or the most representative
  treatment/service line. If no line item or paid service can be read, return null.
- brand_name: brand/manufacturer if visible.
- payment_location: merchant/store name if visible.
- payment_date: purchase date in YYYY-MM-DD if visible.
- total_amount: integer amount paid, without commas or currency symbols. Return null if unclear.
- period_months: free warranty period in months if explicitly visible. Return null if unclear.
"""
_DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"
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


class ReceiptOcrStructuredOutput(BaseModel):
    item_name: str | None = Field(description="영수증에서 추출한 대표 결제 항목명")
    brand_name: str | None = Field(default=None, description="브랜드명")
    payment_location: str | None = Field(default=None, description="구매처")
    payment_date: date | None = Field(default=None, description="구매일")
    total_amount: int | None = Field(default=None, description="총 결제 금액")
    period_months: int | None = Field(default=None, description="무상 AS 기간")

    def to_extracted_fields(self) -> ExtractedReceiptOcrFields:
        return ExtractedReceiptOcrFields(
            item_name=(self.item_name or "").strip(),
            brand_name=self.brand_name,
            payment_location=self.payment_location,
            payment_date=self.payment_date,
            total_amount=self.total_amount,
            period_months=self.period_months,
        )


class ReceiptOcrClientProtocol(Protocol):
    async def extract(self, *, image_uri: str) -> ExtractedReceiptOcrFields: ...


class ReceiptOcrClient:
    """계약 확인용 OCR client.

    실제 AI OCR 연동 전까지 Swagger와 앱 연동 흐름을 먼저 맞추기 위한 구현이다.
    """

    async def extract(self, *, image_uri: str) -> ExtractedReceiptOcrFields:
        structured_output = ReceiptOcrStructuredOutput(
            item_name="테스트 전자제품",
            brand_name="BOAT",
            payment_location="테스트 구매처",
            payment_date=date.today(),
            total_amount=129000,
            period_months=None,
        )
        return structured_output.to_extracted_fields()


class GeminiReceiptOcrClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def extract(self, *, image_uri: str) -> ExtractedReceiptOcrFields:
        try:
            image_part = await _load_image_part(image_uri)
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ReceiptOcrStructuredOutput,
            )
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[image_part, _RECEIPT_OCR_PROMPT],
                config=config,
            )
            structured_output = ReceiptOcrStructuredOutput.model_validate_json(
                response.text or "{}"
            )
            return structured_output.to_extracted_fields()
        except (errors.APIError, httpx.HTTPError, PydanticValidationError) as exception:
            raise ReceiptOcrProviderUnavailableError() from exception


class OpenRouterReceiptOcrClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def extract(self, *, image_uri: str) -> ExtractedReceiptOcrFields:
        try:
            image_url = await _load_openrouter_image_url(image_uri)
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
            KeyError,
            IndexError,
            TypeError,
            httpx.HTTPError,
            PydanticValidationError,
        ) as exception:
            raise ReceiptOcrProviderUnavailableError() from exception


async def _load_image_part(image_uri: str) -> types.Part:
    parsed = urlparse(image_uri)
    if parsed.scheme in {"http", "https"}:
        return await _load_remote_image_part(image_uri)

    image_path = _resolve_local_image_path(image_uri, parsed.scheme)
    image_bytes = await asyncio.to_thread(image_path.read_bytes)
    return types.Part.from_bytes(
        data=image_bytes,
        mime_type=_guess_mime_type(image_path.as_posix()),
    )


async def _load_openrouter_image_url(image_uri: str) -> str:
    parsed = urlparse(image_uri)
    if parsed.scheme in {"http", "https"}:
        return image_uri

    image_path = _resolve_local_image_path(image_uri, parsed.scheme)
    image_bytes = await asyncio.to_thread(image_path.read_bytes)
    mime_type = _guess_mime_type(image_path.as_posix())
    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded_image}"


async def _load_remote_image_part(image_uri: str) -> types.Part:
    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        response = await client.get(image_uri)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    return types.Part.from_bytes(
        data=response.content,
        mime_type=content_type or _guess_mime_type(image_uri),
    )


def _resolve_local_image_path(image_uri: str, scheme: str) -> Path:
    if scheme == "file":
        parsed = urlparse(image_uri)
        path = unquote(parsed.path)
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return Path(path)

    return Path(image_uri)


def _guess_mime_type(source: str) -> str:
    mime_type, _encoding = mimetypes.guess_type(source)
    return mime_type or _DEFAULT_IMAGE_MIME_TYPE
