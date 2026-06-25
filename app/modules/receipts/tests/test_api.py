from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol
from uuid import UUID

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


class _ReceiptOcrClientStub(Protocol):
    async def extract(self, *, image_uri: str) -> _ExtractedReceiptOcrFields: ...


class UnreadableReceiptOcrClient:
    async def extract(self, *, image_uri: str) -> _ExtractedReceiptOcrFields:
        return _ExtractedReceiptOcrFields(
            item_name="",
            brand_name=None,
            payment_location=None,
            payment_date=None,
            total_amount=None,
            period_months=None,
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
    assert data["item_name"] == "삼성 냉장고 875L"
    assert data["payment_date"] == "2024-05-26"
    assert data["total_amount"] == 5137000
    assert data["period_months"] == 24
    assert data["expires_on"] == "2026-05-26"
    assert data["requires_physical_receipt"] is True
    assert data["receipt_file_ids"] == [str(TEST_FILE_ID), str(SECOND_TEST_FILE_ID)]

    async with postgres_session_factory() as session:
        record = await session.get(receipt_orm.Receipt, UUID(data["receipt_id"]))
        attachment_records = await session.scalars(
            select(receipt_orm.ReceiptAttachment).where(
                receipt_orm.ReceiptAttachment.receipt_id == UUID(data["receipt_id"])
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


async def test_create_receipt_accepts_nullable_fields_and_manual_registration(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "item_name": "병원비",
        "payment_date": "2024-06-01",
        "payment_location": None,
        "total_amount": None,
    }

    async with _client(postgres_session_factory) as client:
        response = await client.post("/api/v1/receipts", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["success"] is True
    data = body["data"]
    assert data["brand_name"] is None
    assert data["payment_location"] is None
    assert data["total_amount"] is None
    assert data["period_months"] == 12
    assert data["expires_on"] == "2025-06-01"
    assert data["requires_physical_receipt"] is False
    assert data["receipt_file_ids"] == []


async def test_ocr_failure_can_fall_back_to_manual_receipt_save(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(
        postgres_session_factory,
        receipt_ocr_client=UnreadableReceiptOcrClient(),
    ) as client:
        ocr_response = await client.post(
            "/api/v1/ocr/receipt",
            json={"image_uri": "https://storage.example.com/receipts/unreadable.png"},
        )
        save_response = await client.post(
            "/api/v1/receipts",
            json={
                "item_name": "수동 입력 제품",
                "payment_date": "2024-06-01",
                "payment_location": None,
                "total_amount": None,
            },
        )

    ocr_body = ocr_response.json()
    assert ocr_response.status_code == 422
    assert ocr_body["data"]["errors"] == [
        {
            "field": "image_uri",
            "message": "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요.",
        }
    ]

    save_body = save_response.json()
    assert save_response.status_code == 201
    assert save_body["data"]["item_name"] == "수동 입력 제품"
    assert save_body["data"]["period_months"] == 12
    assert save_body["data"]["expires_on"] == "2025-06-01"


async def test_create_receipt_calculates_expiration_on_month_end(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "item_name": "월말 구매 제품",
        "payment_date": "2024-01-31",
        "period_months": 1,
    }

    async with _client(postgres_session_factory) as client:
        response = await client.post("/api/v1/receipts", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["data"]["expires_on"] == "2024-02-29"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (
            {
                "item_name": "   ",
                "payment_date": "2024-06-01",
            },
            "item_name",
        ),
        (
            {
                "item_name": "미래 구매",
                "payment_date": (date.today() + timedelta(days=1)).isoformat(),
            },
            "payment_date",
        ),
        (
            {
                "item_name": "기간 오류",
                "payment_date": "2024-06-01",
                "period_months": 0,
            },
            "period_months",
        ),
        (
            {
                "item_name": "기간 오류",
                "payment_date": "2024-06-01",
                "period_months": 61,
            },
            "period_months",
        ),
        (
            {
                "item_name": "금액 오류",
                "payment_date": "2024-06-01",
                "total_amount": -1,
            },
            "total_amount",
        ),
        (
            {
                "item_name": "브랜드 길이 오류",
                "payment_date": "2024-06-01",
                "brand_name": "가" * 256,
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
                json={"item_name": "삼성 냉장고", "payment_date": "2024-05-26"},
            )
            body = response.json()
            assert response.status_code == 401
            assert body["success"] is False
            assert body["status"] == 401
            assert body["data"]["path"] == "/api/v1/receipts"
