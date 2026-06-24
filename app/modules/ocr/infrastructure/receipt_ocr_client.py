from __future__ import annotations

import asyncio
import base64
import ipaddress
import mimetypes
import socket
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse

import httpx
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError

_RECEIPT_OCR_PROMPT = """
You are an information extraction specialist for receipts.

Extract only information that is clearly supported by the receipt image.
Do not guess missing or ambiguous values.
If a field is not visible or uncertain, return null.
Normalize dates to YYYY-MM-DD when clearly readable.
Normalize total_amount as an integer number only when clearly readable.
Do not extract serial numbers. Serial number support is out of scope for MVP.
Respond only with the configured structured output.
Write text values in Korean when applicable.
"""
_DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"
_HTTP_TIMEOUT_SECONDS = 10.0
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
_BLOCKED_REMOTE_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
}


@dataclass(frozen=True)
class ExtractedReceiptOcrFields:
    item_name: str
    brand_name: str | None
    payment_location: str | None
    payment_date: date | None
    total_amount: int | None
    period_months: int | None


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
    async def extract(self, *, file_id: str) -> ExtractedReceiptOcrFields: ...


class ReceiptOcrClient:
    """계약 확인용 OCR client.

    실제 AI OCR 연동 전까지 Swagger와 앱 연동 흐름을 먼저 맞추기 위한 구현이다.
    """

    async def extract(self, *, file_id: str) -> ExtractedReceiptOcrFields:
        structured_output = ReceiptOcrStructuredOutput(
            item_name="테스트 전자제품",
            brand_name="BOAT",
            payment_location="테스트 구매처",
            payment_date=date.today(),
            total_amount=129000,
            period_months=None,
        )
        return structured_output.to_extracted_fields()


class OpenRouterReceiptOcrClient:
    def __init__(self, *, api_key: str, model: str, allow_local_files: bool = False) -> None:
        self._api_key = api_key
        self._model = model
        self._allow_local_files = allow_local_files

    async def extract(self, *, file_id: str) -> ExtractedReceiptOcrFields:
        try:
            # ponytail: storage module is not in this repo yet; replace this pass-through
            # with file_id -> stored image URL/bytes resolution when the upload API lands.
            image_url = await _load_openrouter_image_url(
                file_id,
                allow_local_files=self._allow_local_files,
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


async def _load_openrouter_image_url(image_uri: str, *, allow_local_files: bool) -> str:
    parsed = urlparse(image_uri)
    if parsed.scheme in {"http", "https"}:
        await _validate_remote_image_url(image_uri)
        return image_uri

    image_path = _resolve_local_image_path(
        image_uri,
        parsed.scheme,
        allow_local_files=allow_local_files,
    )
    _validate_local_image_size(image_path)
    image_bytes = await asyncio.to_thread(image_path.read_bytes)
    mime_type = _guess_mime_type(image_path.as_posix())
    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded_image}"


def _resolve_local_image_path(image_uri: str, scheme: str, *, allow_local_files: bool) -> Path:
    if not allow_local_files:
        raise ValueError("local image files are only allowed in local/test environments")

    if scheme == "file":
        parsed = urlparse(image_uri)
        path = unquote(parsed.path)
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return Path(path)

    if scheme and not _is_windows_drive_scheme(scheme, image_uri):
        raise ValueError(f"unsupported image uri scheme: {scheme}")

    return Path(image_uri)


def _validate_local_image_size(image_path: Path) -> None:
    if image_path.stat().st_size > _MAX_IMAGE_BYTES:
        raise ValueError("image file is too large")


async def _validate_remote_image_url(image_uri: str) -> None:
    parsed = urlparse(image_uri)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported remote image uri scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("remote image uri must include a host")

    normalized_hostname = hostname.rstrip(".").lower()
    if (
        normalized_hostname in _BLOCKED_REMOTE_HOSTNAMES
        or normalized_hostname.endswith(".localhost")
        or normalized_hostname.endswith(".local")
    ):
        raise ValueError("remote image host is not allowed")

    try:
        _validate_public_ip_address(ipaddress.ip_address(normalized_hostname))
        return
    except ValueError:
        pass

    addresses = await asyncio.to_thread(_resolve_hostname, normalized_hostname)
    for address in addresses:
        _validate_public_ip_address(ipaddress.ip_address(address))


def _resolve_hostname(hostname: str) -> set[str]:
    return {
        str(address_info[4][0])
        for address_info in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    }


def _validate_public_ip_address(ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if (
        ip_address.is_loopback
        or ip_address.is_private
        or ip_address.is_link_local
        or ip_address.is_multicast
        or ip_address.is_reserved
        or ip_address.is_unspecified
    ):
        raise ValueError("remote image host resolves to a blocked address")


def _is_windows_drive_scheme(scheme: str, image_uri: str) -> bool:
    return len(scheme) == 1 and image_uri[1:3] in {":\\", ":/"}


def _guess_mime_type(source: str) -> str:
    mime_type, _encoding = mimetypes.guess_type(source)
    return mime_type or _DEFAULT_IMAGE_MIME_TYPE
