import calendar
from collections.abc import Callable
from datetime import date

import pytest
from httpx import AsyncClient

from app.core.config.settings import Settings
from app.core.domain.exceptions import ValidationError
from app.modules.ocr.api.diagnostic_route import OcrDiagnosticRoute
from app.modules.ocr.api.router import router as ocr_router
from app.modules.ocr.application.ports.receipt_ocr_client import (
    ExtractedReceiptOcrFields,
    ReceiptOcrImage,
)
from app.modules.ocr.dependencies import get_receipt_ocr_client
from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError
from app.modules.ocr.domain.model import ReceiptOcrResult
from app.modules.ocr.domain.value_objects import BrandName, ItemName, PaymentLocation, TotalAmount
from app.modules.ocr.tests.conftest import RecordingUseCreditCommandUseCase

_PNG_BYTES = b"\x89PNG\r\n\x1a\nreceipt-image"


class UnreadableReceiptOcrClient:
    async def extract(self, *, images: tuple[ReceiptOcrImage, ...]) -> ExtractedReceiptOcrFields:
        return ExtractedReceiptOcrFields(
            item_name="",
            brand_name=None,
            serial_number=None,
            payment_location=None,
            payment_date=None,
            total_amount=None,
            period_months=None,
            category=None,
            sub_category=None,
            unreadable_file_indexes=tuple(image.file_index for image in images),
        )


class PartiallyUnreadableReceiptOcrClient:
    def __init__(self) -> None:
        self.images: tuple[ReceiptOcrImage, ...] = ()

    async def extract(self, *, images: tuple[ReceiptOcrImage, ...]) -> ExtractedReceiptOcrFields:
        self.images = images
        return ExtractedReceiptOcrFields(
            item_name="삼성 냉장고",
            brand_name="삼성",
            serial_number=None,
            payment_location="전자랜드",
            payment_date=date.today(),
            total_amount=129000,
            period_months=12,
            category="주방 가전",
            sub_category="냉장고",
            unreadable_file_indexes=(1,),
        )


class ProviderUnavailableReceiptOcrClient:
    async def extract(self, *, images: tuple[ReceiptOcrImage, ...]) -> ExtractedReceiptOcrFields:
        raise ReceiptOcrProviderUnavailableError()


class ZeroTotalAmountReceiptOcrClient:
    async def extract(self, *, images: tuple[ReceiptOcrImage, ...]) -> ExtractedReceiptOcrFields:
        return ExtractedReceiptOcrFields(
            item_name="무상 교체",
            brand_name=None,
            serial_number=None,
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


def test_receipt_ocr_result_uses_category_fallback() -> None:
    result = ReceiptOcrResult.create(
        item_name="삼성 냉장고 875L",
        brand_name="삼성",
        serial_number=" SN-20240526-001 ",
        payment_location="전자랜드",
        payment_date=date.today(),
        total_amount=5137000,
        period_months=12,
        category=None,
        sub_category=None,
    )

    assert result.serial_number == "SN-20240526-001"
    assert result.category == "기타 기기"
    assert result.sub_category == "기타"


async def test_receipt_ocr_dependency_rejects_missing_provider_in_non_local_env() -> None:
    settings = Settings(app_env="dev", openrouter_api_key=None)

    with pytest.raises(ReceiptOcrProviderUnavailableError):
        await get_receipt_ocr_client(settings)


async def test_receipt_ocr_endpoint_returns_contract_response(client: AsyncClient) -> None:
    today = date.today()
    last_day = calendar.monthrange(today.year + 1, today.month)[1]
    expected_expires_on = date(today.year + 1, today.month, min(today.day, last_day))

    response = await client.post(
        "/api/v1/ocr",
        files={"file": ("receipt.png", _PNG_BYTES, "image/png")},
    )

    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["status"] == 200
    assert body["data"] == {
        "item_name": "삼성 냉장고 875L",
        "brand_name": "삼성",
        "serial_number": "SN-20240526-001",
        "payment_location": "테스트 구매처",
        "payment_date": today.isoformat(),
        "total_amount": 129000,
        "period_months": 12,
        "expires_on": expected_expires_on.isoformat(),
        "category": "주방 가전",
        "sub_category": "냉장고",
        "needs_review": True,
        "warnings": ["무상 AS 기간을 찾지 못해 12개월 기본값을 적용했습니다."],
    }


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
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING")

    response = await client.post("/api/v1/ocr", data={})

    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["message"] == "요청 값이 올바르지 않습니다."
    assert body["data"]["path"] == "/api/v1/ocr"
    assert body["data"]["errors"] == [{"field": "file", "message": "Field required"}]
    assert "ocr_request_validation_failed" in caplog.text
    assert "fields=('file',)" in caplog.text
    assert "error_types=('missing',)" in caplog.text
    assert "RequestValidationError" in caplog.text


async def test_receipt_ocr_endpoint_accepts_multiple_file_parts(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/ocr",
        files=[
            ("file", ("receipt-1.png", _PNG_BYTES, "image/png")),
            ("file", ("receipt-2.png", _PNG_BYTES, "image/png")),
        ],
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


async def test_receipt_ocr_endpoint_rejects_more_than_five_file_parts(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING")

    response = await client.post(
        "/api/v1/ocr",
        files=[("file", (f"receipt-{index}.png", _PNG_BYTES, "image/png")) for index in range(6)],
    )

    body = response.json()

    assert response.status_code == 422
    assert body["data"]["errors"] == [
        {"field": "files", "message": "파일은 최대 5개까지 업로드할 수 있습니다."}
    ]
    assert "ocr_upload_validation_failed" in caplog.text
    assert "image_count=6" in caplog.text
    assert "content_types=('image/png', 'image/png'" in caplog.text
    assert "exception_type=ValidationError" in caplog.text
    assert "receipt-0.png" not in caplog.text
    assert repr(_PNG_BYTES) not in caplog.text


async def test_receipt_ocr_endpoint_returns_unreadable_image_failure(
    client: AsyncClient,
    override_receipt_ocr_client: Callable[[UnreadableReceiptOcrClient], None],
    use_recording_credit_reservation_command_use_case: RecordingUseCreditCommandUseCase,
    use_recording_credit_command_use_case: RecordingUseCreditCommandUseCase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING")
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
            "fileIndex": 0,
            "message": "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요.",
        }
    ]
    assert len(use_recording_credit_reservation_command_use_case.commands) == 1
    assert use_recording_credit_command_use_case.commands == []
    assert "ocr_analysis_failed reason=unreadable_image" in caplog.text
    assert "image_count=1" in caplog.text
    assert "content_types=('image/png',)" in caplog.text
    assert "file_indexes=(0,)" in caplog.text
    assert "exception_type=ReceiptImageUnreadableError" in caplog.text
    assert repr(_PNG_BYTES) not in caplog.text


async def test_receipt_ocr_endpoint_returns_only_unreadable_file_indexes(
    client: AsyncClient,
    override_receipt_ocr_client: Callable[[PartiallyUnreadableReceiptOcrClient], None],
    use_recording_credit_command_use_case: RecordingUseCreditCommandUseCase,
) -> None:
    ocr_client = PartiallyUnreadableReceiptOcrClient()
    override_receipt_ocr_client(ocr_client)

    response = await client.post(
        "/api/v1/ocr",
        files=[
            ("file", ("receipt-1.png", _PNG_BYTES, "image/png")),
            ("file", ("receipt-2.png", _PNG_BYTES, "image/png")),
            ("file", ("receipt-3.png", _PNG_BYTES, "image/png")),
        ],
    )

    body = response.json()

    assert response.status_code == 422
    assert body["data"]["errors"] == [
        {
            "field": "file",
            "fileIndex": 1,
            "message": "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요.",
        }
    ]
    assert [image.file_index for image in ocr_client.images] == [0, 1, 2]
    assert [image.content for image in ocr_client.images] == [_PNG_BYTES] * 3
    assert use_recording_credit_command_use_case.commands == []


async def test_receipt_ocr_endpoint_returns_provider_unavailable_failure(
    client: AsyncClient,
    override_receipt_ocr_client: Callable[[ProviderUnavailableReceiptOcrClient], None],
    use_recording_credit_reservation_command_use_case: RecordingUseCreditCommandUseCase,
    use_recording_credit_command_use_case: RecordingUseCreditCommandUseCase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING")
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
    assert "ocr_analysis_failed reason=provider_unavailable" in caplog.text
    assert "file_indexes=()" in caplog.text
    assert "exception_type=ReceiptOcrProviderUnavailableError" in caplog.text
    assert repr(_PNG_BYTES) not in caplog.text


async def test_receipt_ocr_endpoint_openapi_examples(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    operation = response.json()["paths"]["/api/v1/ocr"]["post"]
    success_example = operation["responses"]["200"]["content"]["application/json"]["example"]
    validation_examples = operation["responses"]["422"]["content"]["application/json"]["examples"]
    unreadable_example = validation_examples["unreadable_images"]["value"]
    invalid_upload_example = validation_examples["invalid_upload"]["value"]
    insufficient_credit_example = operation["responses"]["409"]["content"]["application/json"][
        "example"
    ]
    provider_unavailable_example = operation["responses"]["503"]["content"]["application/json"][
        "example"
    ]

    assert operation["summary"] == "영수증 OCR 분석"
    assert success_example["data"]["item_name"] == "삼성 냉장고 875L"
    assert success_example["data"]["serial_number"] == "SN-20240526-001"
    assert success_example["data"]["category"] == "주방 가전"
    assert success_example["data"]["sub_category"] == "냉장고"
    assert success_example["data"]["needs_review"] is True
    assert unreadable_example["data"]["errors"][0]["field"] == "file"
    assert unreadable_example["data"]["errors"][0]["fileIndex"] == 1
    assert invalid_upload_example["data"]["errors"][0] == {
        "field": "files",
        "message": "파일은 최대 5개까지 업로드할 수 있습니다.",
    }
    assert insufficient_credit_example["data"]["message"] == "사용 가능한 크레딧이 부족합니다."
    assert provider_unavailable_example["status"] == 503


async def test_receipt_ocr_endpoint_openapi_uses_multipart_file(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    operation = response.json()["paths"]["/api/v1/ocr"]["post"]
    request_content = operation["requestBody"]["content"]

    assert "multipart/form-data" in request_content
    assert "application/json" not in request_content


def test_receipt_ocr_router_owns_request_validation_logging() -> None:
    assert ocr_router.route_class is OcrDiagnosticRoute
