import calendar
from collections.abc import Callable
from datetime import date

import pytest
from httpx import AsyncClient

from app.core.config.settings import Settings
from app.core.domain.exceptions import ValidationError
from app.modules.ocr.dependencies import get_receipt_ocr_client
from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError
from app.modules.ocr.domain.value_objects import BrandName, ItemName, PaymentLocation, TotalAmount
from app.modules.ocr.infrastructure.receipt_ocr_client import ExtractedReceiptOcrFields


class UnreadableReceiptOcrClient:
    async def extract(self, *, file_id: str) -> ExtractedReceiptOcrFields:
        return ExtractedReceiptOcrFields(
            item_name="",
            brand_name=None,
            payment_location=None,
            payment_date=None,
            total_amount=None,
            period_months=None,
        )


class ProviderUnavailableReceiptOcrClient:
    async def extract(self, *, file_id: str) -> ExtractedReceiptOcrFields:
        raise ReceiptOcrProviderUnavailableError()


def test_item_name_rejects_whitespace_only_value() -> None:
    with pytest.raises(ValidationError):
        ItemName("   ")


@pytest.mark.parametrize(
    ("value_object", "value"),
    [
        (BrandName, "   "),
        (PaymentLocation, "   "),
        (TotalAmount, -1),
    ],
)
def test_receipt_ocr_value_objects_reject_invalid_values(value_object: type, value: object) -> None:
    with pytest.raises(ValidationError):
        value_object(value)


async def test_receipt_ocr_dependency_rejects_missing_provider_in_non_local_env() -> None:
    settings = Settings(app_env="dev", openrouter_api_key=None)

    with pytest.raises(ReceiptOcrProviderUnavailableError):
        await get_receipt_ocr_client(settings)


async def test_receipt_ocr_endpoint_returns_contract_response(client: AsyncClient) -> None:
    today = date.today()
    last_day = calendar.monthrange(today.year + 1, today.month)[1]
    expected_expires_on = date(today.year + 1, today.month, min(today.day, last_day))

    response = await client.post(
        "/api/v1/ocr/receipt",
        json={"file_id": "sample-receipt-file-id"},
    )

    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["status"] == 200
    assert body["data"] == {
        "item_name": "테스트 전자제품",
        "brand_name": "BOAT",
        "payment_location": "테스트 구매처",
        "payment_date": today.isoformat(),
        "total_amount": 129000,
        "period_months": 12,
        "expires_on": expected_expires_on.isoformat(),
        "needs_review": True,
        "warnings": ["무상 AS 기간을 찾지 못해 12개월 기본값을 적용했습니다."],
    }


async def test_receipt_ocr_endpoint_uses_request_validation_envelope(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/v1/ocr/receipt", json={})

    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["message"] == "요청 값이 올바르지 않습니다."
    assert body["data"]["path"] == "/api/v1/ocr/receipt"
    assert body["data"]["errors"] == [{"field": "file_id", "message": "Field required"}]


async def test_receipt_ocr_endpoint_returns_unreadable_image_failure(
    client: AsyncClient,
    override_receipt_ocr_client: Callable[[UnreadableReceiptOcrClient], None],
) -> None:
    override_receipt_ocr_client(UnreadableReceiptOcrClient())

    response = await client.post(
        "/api/v1/ocr/receipt",
        json={"file_id": "unreadable-receipt-file-id"},
    )

    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["message"] == "입력값이 올바르지 않습니다."
    assert body["data"]["path"] == "/api/v1/ocr/receipt"
    assert body["data"]["errors"] == [
        {
            "field": "file_id",
            "message": "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요.",
        }
    ]


async def test_receipt_ocr_endpoint_returns_provider_unavailable_failure(
    client: AsyncClient,
    override_receipt_ocr_client: Callable[[ProviderUnavailableReceiptOcrClient], None],
) -> None:
    override_receipt_ocr_client(ProviderUnavailableReceiptOcrClient())

    response = await client.post(
        "/api/v1/ocr/receipt",
        json={"file_id": "sample-receipt-file-id"},
    )

    body = response.json()

    assert response.status_code == 503
    assert body["success"] is False
    assert body["status"] == 503
    assert (
        body["data"]["message"]
        == "OCR 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요."
    )
    assert body["data"]["path"] == "/api/v1/ocr/receipt"
    assert body["data"]["errors"] == []


async def test_receipt_ocr_endpoint_openapi_examples(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    operation = response.json()["paths"]["/api/v1/ocr/receipt"]["post"]
    success_example = operation["responses"]["200"]["content"]["application/json"]["example"]
    unreadable_example = operation["responses"]["422"]["content"]["application/json"]["example"]
    provider_unavailable_example = operation["responses"]["503"]["content"]["application/json"][
        "example"
    ]

    assert operation["summary"] == "영수증 OCR 분석"
    assert success_example["data"]["item_name"] == "삼성 냉장고 875L"
    assert success_example["data"]["needs_review"] is True
    assert unreadable_example["data"]["errors"][0]["field"] == "file_id"
    assert provider_unavailable_example["status"] == 503
