from collections.abc import Callable
from datetime import date

import pytest
from httpx import AsyncClient

from app.core.config.settings import Settings
from app.core.domain.exceptions import ValidationError
from app.modules.ocr.application.ports.receipt_ocr_client import ExtractedReceiptOcrFields
from app.modules.ocr.dependencies import get_receipt_ocr_client
from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError
from app.modules.ocr.domain.model import ReceiptOcrResult
from app.modules.ocr.domain.value_objects import BrandName, ItemName, PaymentLocation, TotalAmount
from app.modules.ocr.tests.conftest import RecordingUseCreditCommandUseCase

_PNG_BYTES = b"\x89PNG\r\n\x1a\nreceipt-image"


class UnreadableReceiptOcrClient:
    async def extract(
        self, *, image_content: bytes, content_type: str
    ) -> ExtractedReceiptOcrFields:
        return ExtractedReceiptOcrFields(
            item_name="",
            brand_name=None,
            payment_location=None,
            payment_date=None,
            total_amount=None,
            period_months=None,
            category=None,
            sub_category=None,
        )


class ProviderUnavailableReceiptOcrClient:
    async def extract(
        self, *, image_content: bytes, content_type: str
    ) -> ExtractedReceiptOcrFields:
        raise ReceiptOcrProviderUnavailableError()


class ZeroTotalAmountReceiptOcrClient:
    async def extract(
        self, *, image_content: bytes, content_type: str
    ) -> ExtractedReceiptOcrFields:
        return ExtractedReceiptOcrFields(
            item_name="무상 교체",
            brand_name=None,
            payment_location=None,
            payment_date=date.today(),
            total_amount=0,
            period_months=12,
            category=None,
            sub_category=None,
        )


def test_item_name_rejects_whitespace_only_value() -> None:
    with pytest.raises(ValidationError):
        ItemName("   ")


def test_receipt_ocr_brand_name_rejects_whitespace_only_value() -> None:
    with pytest.raises(ValidationError):
        BrandName("   ")


def test_receipt_ocr_payment_location_rejects_whitespace_only_value() -> None:
    with pytest.raises(ValidationError):
        PaymentLocation("   ")


def test_receipt_ocr_total_amount_rejects_negative_value() -> None:
    with pytest.raises(ValidationError):
        TotalAmount(-1)


def test_receipt_ocr_result_drops_sub_category_without_category() -> None:
    result = ReceiptOcrResult.create(
        item_name="삼성 냉장고 875L",
        brand_name="삼성",
        payment_location="전자랜드",
        payment_date=date.today(),
        total_amount=5137000,
        period_months=12,
        category=None,
        sub_category="냉장고",
    )

    assert result.category is None
    assert result.sub_category is None


async def test_receipt_ocr_dependency_rejects_missing_provider_in_non_local_env() -> None:
    settings = Settings(app_env="dev", openrouter_api_key=None)

    with pytest.raises(ReceiptOcrProviderUnavailableError):
        await get_receipt_ocr_client(settings)


async def test_receipt_ocr_endpoint_keeps_zero_total_amount(
    client: AsyncClient,
    override_receipt_ocr_client: Callable[[ZeroTotalAmountReceiptOcrClient], None],
) -> None:
    override_receipt_ocr_client(ZeroTotalAmountReceiptOcrClient())

    response = await client.post(
        "/api/v1/ocr",
        files={"file": ("receipt.png", _PNG_BYTES, "image/png")},
    )

    body = response.json()

    assert response.status_code == 200
    assert body["data"]["total_amount"] == 0


async def test_receipt_ocr_endpoint_uses_request_validation_envelope(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/v1/ocr", data={})

    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["message"] == "요청 값이 올바르지 않습니다."
    assert body["data"]["path"] == "/api/v1/ocr"
    assert body["data"]["errors"] == [{"field": "file", "message": "Field required"}]


async def test_receipt_ocr_endpoint_rejects_multiple_file_parts(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/ocr",
        files=[
            ("file", ("receipt-1.png", _PNG_BYTES, "image/png")),
            ("file", ("receipt-2.png", _PNG_BYTES, "image/png")),
        ],
    )

    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["path"] == "/api/v1/ocr"
    assert body["data"]["errors"] == [
        {"field": "files", "message": "파일은 최대 1개까지 업로드할 수 있습니다."}
    ]


async def test_receipt_ocr_endpoint_returns_unreadable_image_failure(
    client: AsyncClient,
    override_receipt_ocr_client: Callable[[UnreadableReceiptOcrClient], None],
    use_recording_credit_reservation_command_use_case: RecordingUseCreditCommandUseCase,
    use_recording_credit_command_use_case: RecordingUseCreditCommandUseCase,
) -> None:
    override_receipt_ocr_client(UnreadableReceiptOcrClient())

    response = await client.post(
        "/api/v1/ocr",
        files={"file": ("receipt.png", _PNG_BYTES, "image/png")},
    )

    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["message"] == "입력값이 올바르지 않습니다."
    assert body["data"]["path"] == "/api/v1/ocr"
    assert body["data"]["errors"] == [
        {
            "field": "file",
            "message": "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요.",
        }
    ]
    assert len(use_recording_credit_reservation_command_use_case.commands) == 1
    assert use_recording_credit_command_use_case.commands == []


async def test_receipt_ocr_endpoint_returns_provider_unavailable_failure(
    client: AsyncClient,
    override_receipt_ocr_client: Callable[[ProviderUnavailableReceiptOcrClient], None],
    use_recording_credit_reservation_command_use_case: RecordingUseCreditCommandUseCase,
    use_recording_credit_command_use_case: RecordingUseCreditCommandUseCase,
) -> None:
    override_receipt_ocr_client(ProviderUnavailableReceiptOcrClient())

    response = await client.post(
        "/api/v1/ocr",
        files={"file": ("receipt.png", _PNG_BYTES, "image/png")},
    )

    body = response.json()

    assert response.status_code == 503
    assert body["success"] is False
    assert body["status"] == 503
    assert (
        body["data"]["message"]
        == "OCR 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요."
    )
    assert body["data"]["path"] == "/api/v1/ocr"
    assert body["data"]["errors"] == []
    assert len(use_recording_credit_reservation_command_use_case.commands) == 1
    assert use_recording_credit_command_use_case.commands == []


async def test_receipt_ocr_endpoint_openapi_examples(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    operation = response.json()["paths"]["/api/v1/ocr"]["post"]
    success_example = operation["responses"]["200"]["content"]["application/json"]["example"]
    unreadable_example = operation["responses"]["422"]["content"]["application/json"]["example"]
    provider_unavailable_example = operation["responses"]["503"]["content"]["application/json"][
        "example"
    ]

    assert operation["summary"] == "영수증 OCR 분석"
    assert success_example["data"]["item_name"] == "삼성 냉장고 875L"
    assert success_example["data"]["category"] == "주방 가전"
    assert success_example["data"]["sub_category"] == "냉장고"
    assert success_example["data"]["needs_review"] is True
    assert unreadable_example["data"]["errors"][0]["field"] == "file"
    assert provider_unavailable_example["status"] == 503


async def test_receipt_ocr_endpoint_openapi_uses_multipart_file(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    operation = response.json()["paths"]["/api/v1/ocr"]["post"]
    request_content = operation["requestBody"]["content"]

    assert "multipart/form-data" in request_content
    assert "application/json" not in request_content
