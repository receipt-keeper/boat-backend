from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config.settings import Settings
from app.core.http.auth import set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.main import create_app
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.ocr.dependencies import get_receipt_ocr_client
from app.modules.receipts.infrastructure.persistence import orm as receipt_orm

TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000101")
TEST_CREDENTIALS_ID = UUID("00000000-0000-0000-0000-000000000102")
TEST_SESSION_ID = UUID("00000000-0000-0000-0000-000000000103")
TEST_FILE_ID = UUID("00000000-0000-0000-0000-000000000201")
SECOND_TEST_FILE_ID = UUID("00000000-0000-0000-0000-000000000202")
PNG_BYTES = b"\x89PNG\r\n\x1a\nreceipt-image"
TEST_SETTINGS = Settings(
    jwt_secret_key="x" * 48,
    jwt_issuer="boat-backend-test",
    jwt_audience="boat-api-test",
)


@dataclass(frozen=True)
class _ExtractedReceiptOcrFields:
    item_name: str
    brand_name: str | None
    payment_location: str | None
    payment_date: date | None
    total_amount: int | None
    period_months: int | None
    category: str | None


class _ReceiptOcrClientStub(Protocol):
    async def extract(
        self,
        *,
        image_content: bytes,
        content_type: str,
    ) -> _ExtractedReceiptOcrFields: ...


class UnreadableReceiptOcrClient:
    async def extract(
        self,
        *,
        image_content: bytes,
        content_type: str,
    ) -> _ExtractedReceiptOcrFields:
        assert image_content == PNG_BYTES
        assert content_type == "image/png"
        return _ExtractedReceiptOcrFields(
            item_name="",
            brand_name=None,
            payment_location=None,
            payment_date=None,
            total_amount=None,
            period_months=None,
            category=None,
        )


class CategoryReceiptOcrClient:
    async def extract(
        self,
        *,
        image_content: bytes,
        content_type: str,
    ) -> _ExtractedReceiptOcrFields:
        assert image_content == PNG_BYTES
        assert content_type == "image/png"
        return _ExtractedReceiptOcrFields(
            item_name="삼성 냉장고 875L",
            brand_name="삼성",
            payment_location="전자랜드",
            payment_date=date(2024, 5, 26),
            total_amount=5137000,
            period_months=24,
            category="가전",
        )


async def _fake_authenticate_current_principal(request: Request) -> AuthenticatedPrincipal:
    principal = AuthenticatedPrincipal(
        user_id=TEST_USER_ID,
        credentials_id=TEST_CREDENTIALS_ID,
        session_id=TEST_SESSION_ID,
        role="user",
    )
    set_current_principal(request, principal)
    return principal


@asynccontextmanager
async def _client(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    authenticated: bool = True,
    receipt_ocr_client: _ReceiptOcrClientStub | None = None,
) -> AsyncIterator[AsyncClient]:
    test_app = create_app(TEST_SETTINGS)
    test_app.state.session_factory = session_factory
    if authenticated:
        test_app.dependency_overrides[authenticate_current_principal] = (
            _fake_authenticate_current_principal
        )
    if receipt_ocr_client is not None:
        test_app.dependency_overrides[get_receipt_ocr_client] = lambda: receipt_ocr_client

    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        test_app.dependency_overrides.clear()


async def _create_receipt(
    client: AsyncClient,
    *,
    item_name: str,
    payment_date: date,
    brand_name: str | None = None,
    payment_location: str | None = None,
    total_amount: int | None = None,
    period_months: int | None = None,
    category: str | None = None,
    memo: str | None = None,
    requires_physical_receipt: bool = True,
    receipt_file_ids: list[UUID] | None = None,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/receipts",
        json={
            "item_name": item_name,
            "brand_name": brand_name,
            "payment_location": payment_location,
            "payment_date": payment_date.isoformat(),
            "total_amount": total_amount,
            "period_months": period_months,
            "category": category,
            "memo": memo,
            "requires_physical_receipt": requires_physical_receipt,
            "receipt_file_ids": [
                str(file_id)
                for file_id in (
                    receipt_file_ids if receipt_file_ids is not None else [TEST_FILE_ID, uuid4()]
                )
            ],
        },
    )
    body = response.json()
    assert response.status_code == 201
    return body["data"]


async def test_create_receipt_persists_final_values(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "item_name": "삼성 냉장고 875L",
        "brand_name": "삼성",
        "payment_location": "전자랜드",
        "payment_date": "2024-05-26",
        "total_amount": 5137000,
        "period_months": 24,
        "category": "가전",
        "memo": "OCR 결과 확인 후 저장",
        "requires_physical_receipt": True,
        "receipt_file_ids": [str(TEST_FILE_ID), str(SECOND_TEST_FILE_ID)],
    }

    async with _client(postgres_session_factory) as client:
        response = await client.post("/api/v1/receipts", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["success"] is True
    assert body["status"] == 201
    data = body["data"]
    assert data["itemName"] == "삼성 냉장고 875L"
    assert data["paymentDate"] == "2024-05-26"
    assert data["totalAmount"] == 5137000
    assert data["periodMonths"] == 24
    assert data["expiresOn"] == "2026-05-26"
    assert data["requiresPhysicalReceipt"] is True
    assert data["receiptFileIds"] == [str(TEST_FILE_ID), str(SECOND_TEST_FILE_ID)]

    async with postgres_session_factory() as session:
        record = await session.get(receipt_orm.Receipt, UUID(data["receiptId"]))
        attachment_records = await session.scalars(
            select(receipt_orm.ReceiptAttachment).where(
                receipt_orm.ReceiptAttachment.receipt_id == UUID(data["receiptId"])
            )
        )
        attachments = tuple(attachment_records)

    assert record is not None
    assert record.user_id == TEST_USER_ID
    assert record.item_name == "삼성 냉장고 875L"
    assert record.payment_location == "전자랜드"
    assert record.total_amount == 5137000
    assert record.requires_physical_receipt is True
    assert {attachment.file_id for attachment in attachments} == {
        TEST_FILE_ID,
        SECOND_TEST_FILE_ID,
    }


def test_receipts_expose_final_registration_route_only() -> None:
    schema = create_app(TEST_SETTINGS).openapi()
    paths = schema["paths"]

    assert set(paths["/api/v1/receipts"]) == {"get", "post"}
    assert set(paths["/api/v1/receipts/{receipt_id}"]) == {"get", "patch", "delete"}
    assert "/api/v1/receipts/recent" not in paths
    assert "/api/v1/receipts/warranty-expirations" not in paths
    assert "/api/v1/assets" not in paths


def test_receipts_openapi_includes_app_test_examples() -> None:
    schema = create_app(TEST_SETTINGS).openapi()
    paths = schema["paths"]

    list_operation = paths["/api/v1/receipts"]["get"]
    create_operation = paths["/api/v1/receipts"]["post"]
    detail_operation = paths["/api/v1/receipts/{receipt_id}"]["get"]
    update_operation = paths["/api/v1/receipts/{receipt_id}"]["patch"]
    delete_operation = paths["/api/v1/receipts/{receipt_id}"]["delete"]

    list_examples = list_operation["responses"]["200"]["content"]["application/json"]["examples"]
    create_request_examples = create_operation["requestBody"]["content"]["application/json"][
        "examples"
    ]
    update_request_examples = update_operation["requestBody"]["content"]["application/json"][
        "examples"
    ]
    create_request_properties = schema["components"]["schemas"]["CreateReceiptRequest"][
        "properties"
    ]
    receipt_response_properties = schema["components"]["schemas"]["ReceiptResponse"]["properties"]
    create_response_example = create_operation["responses"]["201"]["content"]["application/json"][
        "example"
    ]
    detail_response_example = detail_operation["responses"]["200"]["content"]["application/json"][
        "example"
    ]
    update_response_example = update_operation["responses"]["200"]["content"]["application/json"][
        "example"
    ]
    delete_response_example = delete_operation["responses"]["200"]["content"]["application/json"][
        "example"
    ]

    assert list_examples["with_receipts"]["value"]["data"]["receipts"][0]["itemName"] == (
        "삼성 냉장고 875L"
    )
    assert list_examples["empty"]["value"]["data"]["receipts"] == []
    assert create_request_examples["ocr_reviewed"]["value"]["receipt_file_ids"] == [
        "00000000-0000-0000-0000-000000000201"
    ]
    assert "total_amount" not in create_request_examples["manual_nullable"]["value"]
    assert {"type": "null"} in create_request_properties["total_amount"]["anyOf"]
    assert create_response_example["status"] == 201
    assert create_response_example["data"]["receiptFileIds"] == [
        "00000000-0000-0000-0000-000000000201"
    ]
    assert detail_response_example["data"]["itemName"] == "삼성 냉장고 875L"
    assert {"type": "null"} in receipt_response_properties["imageUrl"]["anyOf"]
    assert update_request_examples["partial_update"]["value"]["item_name"] == "삼성 냉장고 900L"
    assert "paymentLocation" not in update_response_example["data"]
    assert delete_response_example == {"success": True, "status": 200}


async def test_list_receipts_supports_home_list_and_search_contract(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(postgres_session_factory) as client:
        first_receipt = await _create_receipt(
            client,
            item_name="삼성 냉장고 875L",
            brand_name="삼성",
            payment_location="전자랜드",
            payment_date=date.today() - timedelta(days=16),
            total_amount=5137000,
            period_months=1,
            category="주방 가전",
            memo="주방 냉장고",
        )
        await _create_receipt(
            client,
            item_name="LG 세탁기",
            brand_name="LG",
            payment_location="하이마트",
            payment_date=date.today() - timedelta(days=400),
            total_amount=1290000,
            period_months=1,
            category="세탁/청소",
            memo=None,
        )
        await _create_receipt(
            client,
            item_name="다이슨 청소기",
            brand_name="Dyson",
            payment_location="코스트코",
            payment_date=date.today(),
            total_amount=890000,
            period_months=24,
            category="세탁/청소",
            memo="거실 청소용",
        )
        recent_response = await client.get("/api/v1/receipts?sort=recent&limit=2")
        recent_body = recent_response.json()
        next_cursor = recent_body["data"]["pagination"]["nextCursor"]
        next_response = await client.get(
            f"/api/v1/receipts?sort=recent&limit=2&cursor={next_cursor}"
        )
        invalid_cursor_response = await client.get(
            "/api/v1/receipts?sort=recent&limit=2&cursor=invalid-cursor"
        )
        expiring_response = await client.get(
            "/api/v1/receipts?status=expiring&sort=expiresOn&limit=5"
        )
        active_response = await client.get("/api/v1/receipts?status=active")
        search_response = await client.get("/api/v1/receipts?q=주방")

    next_body = next_response.json()
    invalid_cursor_body = invalid_cursor_response.json()
    expiring_body = expiring_response.json()
    active_body = active_response.json()
    search_body = search_response.json()

    assert recent_response.status_code == 200
    assert recent_body["data"]["totalCount"] == 3
    assert recent_body["data"]["pagination"]["nextCursor"] is not None
    assert recent_body["data"]["pagination"]["nextCursor"] != "2"
    assert recent_body["data"]["pagination"]["hasNext"] is True
    assert recent_body["data"]["pagination"]["limit"] == 2
    assert recent_body["data"]["pagination"]["totalCount"] == 3
    assert recent_body["data"]["receipts"][0]["imageUrl"] is None
    assert next_response.status_code == 200
    assert next_body["data"]["pagination"] == {
        "nextCursor": None,
        "hasNext": False,
        "limit": 2,
        "totalCount": 3,
    }
    assert len(next_body["data"]["receipts"]) == 1
    assert invalid_cursor_response.status_code == 422
    assert invalid_cursor_body["data"]["errors"][0] == {
        "field": "cursor",
        "message": "유효하지 않은 커서입니다.",
    }
    assert expiring_response.status_code == 200
    assert expiring_body["data"]["receipts"][0]["itemName"] == "삼성 냉장고 875L"
    assert 0 <= expiring_body["data"]["receipts"][0]["warrantyDDay"] <= 30
    assert active_response.status_code == 200
    assert {receipt["itemName"] for receipt in active_body["data"]["receipts"]} == {"다이슨 청소기"}
    assert search_response.status_code == 200
    assert search_body["data"]["pagination"]["totalCount"] == 1
    assert search_body["data"]["receipts"][0]["memo"] == "주방 냉장고"
    assert search_body["data"]["receipts"][0]["receiptFileIds"] == first_receipt["receiptFileIds"]


async def test_receipt_detail_update_and_delete_use_persisted_data(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(postgres_session_factory) as client:
        created = await _create_receipt(
            client,
            item_name="삼성 냉장고 875L",
            brand_name="삼성",
            payment_location="전자랜드",
            payment_date=date(2024, 5, 26),
            total_amount=5137000,
            period_months=24,
            category="주방 가전",
            memo="등록 메모",
            requires_physical_receipt=True,
        )
        receipt_id = created["receiptId"]

        detail_response = await client.get(f"/api/v1/receipts/{receipt_id}")
        update_response = await client.patch(
            f"/api/v1/receipts/{receipt_id}",
            json={
                "item_name": "삼성 냉장고 900L",
                "payment_location": None,
                "total_amount": None,
                "category": "가전",
                "memo": "수정 메모",
                "period_months": 36,
                "receipt_file_ids": [str(SECOND_TEST_FILE_ID)],
            },
        )
        delete_response = await client.delete(f"/api/v1/receipts/{receipt_id}")
        missing_response = await client.get(f"/api/v1/receipts/{receipt_id}")

    detail_body = detail_response.json()
    update_body = update_response.json()
    delete_body = delete_response.json()
    missing_body = missing_response.json()

    assert detail_response.status_code == 200
    assert detail_body["data"]["receiptId"] == receipt_id
    assert detail_body["data"]["itemName"] == "삼성 냉장고 875L"
    assert update_response.status_code == 200
    assert update_body["data"]["itemName"] == "삼성 냉장고 900L"
    assert update_body["data"]["paymentLocation"] is None
    assert update_body["data"]["totalAmount"] is None
    assert update_body["data"]["periodMonths"] == 36
    assert update_body["data"]["expiresOn"] == "2027-05-26"
    assert update_body["data"]["category"] == "가전"
    assert update_body["data"]["memo"] == "수정 메모"
    assert update_body["data"]["receiptFileIds"] == [str(SECOND_TEST_FILE_ID)]
    assert delete_response.status_code == 200
    assert delete_body == {"success": True, "status": 200, "data": None}
    assert missing_response.status_code == 404
    assert missing_body["data"]["message"] == "영수증을 찾을 수 없습니다."


async def test_update_receipt_rejects_null_period_months_without_rewriting_default(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(postgres_session_factory) as client:
        created = await _create_receipt(
            client,
            item_name="삼성 냉장고 875L",
            payment_date=date(2024, 5, 26),
            period_months=24,
        )
        receipt_id = created["receiptId"]

        update_response = await client.patch(
            f"/api/v1/receipts/{receipt_id}",
            json={"period_months": None},
        )
        detail_response = await client.get(f"/api/v1/receipts/{receipt_id}")

    update_body = update_response.json()
    detail_body = detail_response.json()

    assert update_response.status_code == 422
    assert update_body["data"]["errors"][0] == {
        "field": "period_months",
        "message": "무상 AS 기간은 필수입니다.",
    }
    assert detail_response.status_code == 200
    assert detail_body["data"]["periodMonths"] == 24
    assert detail_body["data"]["expiresOn"] == "2026-05-26"


async def test_create_receipt_requires_at_least_one_file(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "item_name": "파일 없는 영수증",
        "payment_date": "2024-06-01",
        "receipt_file_ids": [],
    }

    async with _client(postgres_session_factory) as client:
        response = await client.post("/api/v1/receipts", json=payload)

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["data"]["errors"][0]["field"] == "receipt_file_ids"


async def test_create_receipt_accepts_nullable_fields_and_manual_registration(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "item_name": "병원비",
        "payment_date": "2024-06-01",
        "payment_location": None,
        "total_amount": None,
        "receipt_file_ids": [str(TEST_FILE_ID)],
    }

    async with _client(postgres_session_factory) as client:
        response = await client.post("/api/v1/receipts", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["success"] is True
    data = body["data"]
    assert data["brandName"] is None
    assert data["paymentLocation"] is None
    assert data["totalAmount"] is None
    assert data["periodMonths"] == 12
    assert data["expiresOn"] == "2025-06-01"
    assert data["requiresPhysicalReceipt"] is False
    assert data["receiptFileIds"] == [str(TEST_FILE_ID)]


async def test_ocr_failure_can_fall_back_to_manual_receipt_save(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(
        postgres_session_factory,
        receipt_ocr_client=UnreadableReceiptOcrClient(),
    ) as client:
        ocr_response = await client.post(
            "/api/v1/ocr",
            files={"file": ("receipt.png", PNG_BYTES, "image/png")},
        )
        save_response = await client.post(
            "/api/v1/receipts",
            json={
                "item_name": "수동 입력 제품",
                "payment_date": "2024-06-01",
                "payment_location": None,
                "total_amount": None,
                "receipt_file_ids": [str(TEST_FILE_ID)],
            },
        )

    ocr_body = ocr_response.json()
    assert ocr_response.status_code == 422
    assert ocr_body["data"]["errors"] == [
        {
            "field": "file",
            "message": "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요.",
        }
    ]

    save_body = save_response.json()
    assert save_response.status_code == 201
    assert save_body["data"]["itemName"] == "수동 입력 제품"
    assert save_body["data"]["periodMonths"] == 12
    assert save_body["data"]["expiresOn"] == "2025-06-01"


async def test_ocr_auto_fill_category_can_be_saved(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(
        postgres_session_factory,
        receipt_ocr_client=CategoryReceiptOcrClient(),
    ) as client:
        ocr_response = await client.post(
            "/api/v1/ocr",
            files={"file": ("receipt.png", PNG_BYTES, "image/png")},
        )
        assert ocr_response.status_code == 200
        ocr_data = ocr_response.json()["data"]
        save_response = await client.post(
            "/api/v1/receipts",
            json={
                "item_name": ocr_data["item_name"],
                "brand_name": ocr_data["brand_name"],
                "payment_location": ocr_data["payment_location"],
                "payment_date": ocr_data["payment_date"],
                "total_amount": ocr_data["total_amount"],
                "period_months": ocr_data["period_months"],
                "category": ocr_data["category"],
                "receipt_file_ids": [str(TEST_FILE_ID)],
            },
        )

    save_body = save_response.json()
    assert ocr_data["category"] == "가전"
    assert save_response.status_code == 201
    assert save_body["data"]["category"] == "가전"


async def test_create_receipt_calculates_expiration_on_month_end(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "item_name": "월말 구매 제품",
        "payment_date": "2024-01-31",
        "period_months": 1,
        "receipt_file_ids": [str(TEST_FILE_ID)],
    }

    async with _client(postgres_session_factory) as client:
        response = await client.post("/api/v1/receipts", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["data"]["expiresOn"] == "2024-02-29"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (
            {
                "item_name": "   ",
                "payment_date": "2024-06-01",
                "receipt_file_ids": [str(TEST_FILE_ID)],
            },
            "item_name",
        ),
        (
            {
                "item_name": "미래 구매",
                "payment_date": (date.today() + timedelta(days=1)).isoformat(),
                "receipt_file_ids": [str(TEST_FILE_ID)],
            },
            "payment_date",
        ),
        (
            {
                "item_name": "기간 오류",
                "payment_date": "2024-06-01",
                "period_months": 0,
                "receipt_file_ids": [str(TEST_FILE_ID)],
            },
            "period_months",
        ),
        (
            {
                "item_name": "기간 오류",
                "payment_date": "2024-06-01",
                "period_months": 61,
                "receipt_file_ids": [str(TEST_FILE_ID)],
            },
            "period_months",
        ),
        (
            {
                "item_name": "금액 오류",
                "payment_date": "2024-06-01",
                "total_amount": -1,
                "receipt_file_ids": [str(TEST_FILE_ID)],
            },
            "total_amount",
        ),
        (
            {
                "item_name": "브랜드 길이 오류",
                "payment_date": "2024-06-01",
                "brand_name": "가" * 256,
                "receipt_file_ids": [str(TEST_FILE_ID)],
            },
            "brand_name",
        ),
        (
            {
                "item_name": "파일 개수 오류",
                "payment_date": "2024-06-01",
                "receipt_file_ids": [
                    "00000000-0000-0000-0000-000000000201",
                    "00000000-0000-0000-0000-000000000202",
                    "00000000-0000-0000-0000-000000000203",
                    "00000000-0000-0000-0000-000000000204",
                    "00000000-0000-0000-0000-000000000205",
                    "00000000-0000-0000-0000-000000000206",
                ],
            },
            "receipt_file_ids",
        ),
        (
            {
                "item_name": "파일 중복 오류",
                "payment_date": "2024-06-01",
                "receipt_file_ids": [
                    "00000000-0000-0000-0000-000000000201",
                    "00000000-0000-0000-0000-000000000201",
                ],
            },
            "receipt_file_ids",
        ),
    ],
)
async def test_create_receipt_returns_domain_validation_errors(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    payload: dict[str, object],
    field: str,
) -> None:
    async with _client(postgres_session_factory) as client:
        response = await client.post("/api/v1/receipts", json=payload)

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["message"] in {
        "입력값이 올바르지 않습니다.",
        "요청 값이 올바르지 않습니다.",
    }
    assert body["data"]["path"] == "/api/v1/receipts"
    assert body["data"]["errors"][0]["field"] == field


async def test_create_receipt_aggregates_total_amount_domain_error(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "item_name": "   ",
        "payment_date": "2024-06-01",
        "total_amount": -1,
        "receipt_file_ids": [str(TEST_FILE_ID)],
    }

    async with _client(postgres_session_factory) as client:
        response = await client.post("/api/v1/receipts", json=payload)

    body = response.json()
    errors = body["data"]["errors"]
    assert response.status_code == 422
    assert body["data"]["message"] == "입력값이 올바르지 않습니다."
    assert {error["field"] for error in errors} == {"item_name", "total_amount"}
    assert any(
        error["field"] == "total_amount"
        and error["message"] == "총 결제 금액은 0 이상이어야 합니다."
        for error in errors
    )


async def test_create_receipt_rejects_ocr_only_fields(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "item_name": "삼성 냉장고 875L",
        "payment_date": "2024-05-26",
        "image_uri": "local://receipt.png",
        "receipt_file_ids": [str(TEST_FILE_ID)],
    }

    async with _client(postgres_session_factory) as client:
        response = await client.post("/api/v1/receipts", json=payload)

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["data"]["path"] == "/api/v1/receipts"
    assert body["data"]["errors"][0]["field"] == "image_uri"


async def test_create_receipt_requires_bearer_token(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    requests = [
        {},
        {"Authorization": "Bearer invalid-token"},
    ]

    async with _client(postgres_session_factory, authenticated=False) as client:
        for headers in requests:
            response = await client.post(
                "/api/v1/receipts",
                headers=headers,
                json={
                    "item_name": "삼성 냉장고",
                    "payment_date": "2024-05-26",
                    "receipt_file_ids": [str(TEST_FILE_ID)],
                },
            )
            body = response.json()
            assert response.status_code == 401
            assert body["success"] is False
            assert body["status"] == 401
            assert body["data"]["path"] == "/api/v1/receipts"
