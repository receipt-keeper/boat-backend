import json
from typing import Final
from uuid import UUID

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.config.settings import Settings
from app.core.http.auth import set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.main import create_app
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.users.application.queries.current_user_profile.query import CurrentUserProfileQuery
from app.modules.users.application.queries.current_user_profile.result import (
    CurrentUserProfileResult,
)
from app.modules.users.dependencies import get_current_user_profile_query_use_case

TEST_USER_ID: Final = UUID("00000000-0000-0000-0000-000000000101")
TEST_CREDENTIALS_ID: Final = UUID("00000000-0000-0000-0000-000000000102")
TEST_SESSION_ID: Final = UUID("00000000-0000-0000-0000-000000000103")
TEST_SETTINGS: Final = Settings(app_name="Boat Backend")

EXPECTED_PUBLIC_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/api/v1/credits",
        "/api/v1/credits/transactions",
        "/api/v1/receipts",
        "/api/v1/receipts/{receipt_id}",
        "/api/v1/ocr",
        "/api/v1/usage",
        "/api/v1/notifications",
        "/api/v1/notifications/{notification_id}",
        "/api/v1/notifications/settings",
    }
)

FORBIDDEN_PUBLIC_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/api/v1/receipts/recent",
        "/api/v1/receipts/warranty-expirations",
        "/api/v1/receipt-analysis-allowance",
        "/api/v1/app-config",
        "/api/v1/ocr/receipt",
        "/api/v1/billing-orders",
        "/api/v1/document-analyses",
        "/api/v1/notifications/device-token",
        "/api/v1/notification-reads/{notification_id}",
        "/api/v1/notification-settings",
        "/api/v1/warranty-certificates",
        "/api/v1/warranties",
        "/api/v1/warranties/{warranty_id}",
        "/api/v1/registered-products",
        "/api/v1/products",
        "/api/v1/assets",
        "/api/v1/assets/{asset_id}",
        "/api/v1/notifications/devices/{device_id}",
    }
)

FORBIDDEN_OPENAPI_PUBLIC_TERMS: Final[frozenset[str]] = frozenset(
    {
        "mock",
        "계약 확인",
        "분석권",
        "원장",
        "트랜잭션",
        "현재 사용자의",
        "allowance",
        "billing",
        "receipt-analysis",
        "document-analyses",
        "보증 목록",
        "accountId",
    }
)

FORBIDDEN_ME_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "notificationSettings",
        "notificationEnabled",
        "marketingConsent",
        "pushEnabled",
        "warrantyReminderEnabled",
        "pushToken",
        "pushTokenCount",
        "deviceToken",
        "credits",
        "usage",
        "allowance",
    }
)


class CurrentUserProfileQueryUseCaseStub:
    async def execute(self, query: CurrentUserProfileQuery) -> CurrentUserProfileResult:
        return CurrentUserProfileResult(
            user_id=query.user_id,
            email="contract@example.com",
            name="계약 사용자",
            nickname="계약",
            profile_image_url=None,
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


def _contract_app() -> FastAPI:
    test_app = create_app(TEST_SETTINGS)
    test_app.dependency_overrides[authenticate_current_principal] = (
        _fake_authenticate_current_principal
    )
    test_app.dependency_overrides[get_current_user_profile_query_use_case] = lambda: (
        CurrentUserProfileQueryUseCaseStub()
    )
    return test_app


async def test_app_facing_bc_routes_are_published_in_openapi() -> None:
    # Given: 앱 공개 계약을 설명하는 OpenAPI 문서가 있다.
    test_app = create_app(TEST_SETTINGS)

    # When: 현재 앱의 OpenAPI path 목록을 조회한다.
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as test_client:
        response = await test_client.get("/openapi.json")

    paths = set(response.json()["paths"])
    missing_paths = EXPECTED_PUBLIC_PATHS - paths

    # Then: 홈/자산/크레딧/사용량/알림 중심의 공개 path가 모두 노출된다.
    assert response.status_code == 200
    assert not missing_paths, f"missing app-facing public paths: {sorted(missing_paths)}"


async def test_receipt_and_product_leaking_routes_are_absent_from_openapi() -> None:
    # Given: 앱 공개 계약을 설명하는 OpenAPI 문서가 있다.
    test_app = create_app(TEST_SETTINGS)

    # When: 현재 앱의 OpenAPI path 목록을 조회한다.
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as test_client:
        response = await test_client.get("/openapi.json")

    paths = set(response.json()["paths"])
    still_present_paths = FORBIDDEN_PUBLIC_PATHS & paths

    # Then: 영수증/제품/결제 중심으로 새는 기존 공개 path는 남아 있지 않다.
    assert response.status_code == 200
    assert not still_present_paths, (
        f"forbidden public paths still present: {sorted(still_present_paths)}"
    )


def test_public_openapi_does_not_leak_retired_bc_terms() -> None:
    # Given: 앱 공개 계약을 설명하는 OpenAPI 문서가 있다.
    schema = create_app(TEST_SETTINGS).openapi()

    # When: 공개 문서를 텍스트 계약으로 직렬화한다.
    schema_text = json.dumps(schema, ensure_ascii=False).casefold()
    leaked_terms = [
        term for term in FORBIDDEN_OPENAPI_PUBLIC_TERMS if term.casefold() in schema_text
    ]

    # Then: 폐기된 BC/내부 계약 용어는 공개 문서에 남지 않는다.
    assert leaked_terms == []


async def test_credits_usage_response_bodies_match_app_contract() -> None:
    # Given: 인증된 앱 클라이언트가 있다.
    test_app = _contract_app()

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        # When: 크레딧과 사용량 계약 API를 조회한다.
        credits_response = await test_client.get("/api/v1/credits")
        transactions_response = await test_client.get("/api/v1/credits/transactions")
        usage_response = await test_client.get("/api/v1/usage")

    credits_body = credits_response.json()
    transactions_body = transactions_response.json()
    usage_body = usage_response.json()

    # Then: 크레딧 합계 응답은 앱 계약 필드명만 사용한다.
    assert credits_response.status_code == 200
    assert credits_body["data"] == {
        "totalGrantedCount": 10,
        "usedCount": 7,
        "remainingCount": 3,
    }

    # Then: 크레딧 내역 응답은 보상 사유와 수량을 노출한다.
    assert transactions_response.status_code == 200
    assert transactions_body["data"]["transactions"][0]["reason"] == "quizReward"
    assert transactions_body["data"]["transactions"][0]["amount"] == 10

    # Then: 사용량 응답은 영수증 분석 가능 상태만 노출한다.
    assert usage_response.status_code == 200
    assert usage_body["data"]["receiptAnalysis"] == {
        "remainingCount": 3,
        "canAnalyze": True,
    }


async def test_receipts_match_app_contract() -> None:
    test_app = _contract_app()
    receipt_id = "00000000-0000-0000-0000-000000000301"

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        receipts_response = await test_client.get("/api/v1/receipts")
        expiring_response = await test_client.get(
            "/api/v1/receipts?status=expiring&sort=expiresOn&limit=5"
        )
        search_response = await test_client.get("/api/v1/receipts?q=냉장고")
        receipt_response = await test_client.get(f"/api/v1/receipts/{receipt_id}")

    receipts_body = receipts_response.json()
    expiring_body = expiring_response.json()
    search_body = search_response.json()
    receipt_body = receipt_response.json()

    assert receipts_response.status_code == 200
    assert receipts_body["data"]["total_count"] >= 1
    assert "receipt_file_ids" in receipts_body["data"]["receipts"][0]
    assert "support_url" in receipts_body["data"]["receipts"][0]
    assert expiring_response.status_code == 200
    assert expiring_body["data"]["receipts"][0]["warranty_d_day"] == 14
    assert search_response.status_code == 200
    assert search_body["data"]["receipts"][0]["item_name"] == "삼성 냉장고 875L"

    assert receipt_response.status_code == 200
    assert receipt_body["data"]["receipt_file_ids"]


async def test_users_me_response_does_not_leak_split_bc_fields() -> None:
    # Given: 인증된 앱 클라이언트가 있다.
    test_app = _contract_app()

    # When: 내 정보 API를 조회한다.
    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        response = await test_client.get("/api/v1/users/me")

    body = response.json()
    data = body["data"]
    leaked_fields = FORBIDDEN_ME_FIELDS & set(data)

    # Then: users/me는 프로필 계약만 노출하고 알림/크레딧/사용량 계약을 섞지 않는다.
    assert response.status_code == 200
    assert set(data) == {
        "email",
        "name",
        "nickname",
        "profileImageUrl",
    }
    assert leaked_fields == frozenset()
