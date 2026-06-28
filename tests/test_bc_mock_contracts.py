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
        transactions_response = await test_client.get("/api/v1/credits/transactions?limit=1")
        next_transactions_response = await test_client.get(
            "/api/v1/credits/transactions?limit=1&cursor=1"
        )
        usage_response = await test_client.get("/api/v1/usage")

    credits_body = credits_response.json()
    transactions_body = transactions_response.json()
    next_transactions_body = next_transactions_response.json()
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
    assert transactions_body["data"]["pagination"] == {
        "nextCursor": "1",
        "hasNext": True,
        "limit": 1,
        "totalCount": 2,
    }
    assert next_transactions_response.status_code == 200
    assert next_transactions_body["data"]["transactions"][0]["reason"] == "receiptAnalysis"
    assert next_transactions_body["data"]["pagination"] == {
        "nextCursor": None,
        "hasNext": False,
        "limit": 1,
        "totalCount": 2,
    }

    # Then: 사용량 응답은 영수증 분석 가능 상태만 노출한다.
    assert usage_response.status_code == 200
    assert usage_body["data"]["ocr"] == {
        "remainingCount": 3,
        "canAnalyze": True,
    }


async def test_receipts_match_app_contract() -> None:
    schema = create_app(TEST_SETTINGS).openapi()

    receipt_collection = schema["paths"]["/api/v1/receipts"]
    receipt_detail = schema["paths"]["/api/v1/receipts/{receipt_id}"]

    assert set(receipt_collection) == {"get", "post"}
    assert set(receipt_detail) == {
        "get",
        "patch",
        "delete",
    }
    _assert_common_response_schema(schema, receipt_collection["get"], 200)
    _assert_common_response_schema(schema, receipt_collection["post"], 201)
    _assert_common_response_schema(schema, receipt_detail["get"], 200)
    _assert_common_response_schema(schema, receipt_detail["patch"], 200)
    _assert_common_response_schema(schema, receipt_detail["delete"], 200)


def _assert_common_response_schema(
    openapi_schema: dict[str, object],
    operation: dict[str, object],
    status_code: int,
) -> None:
    responses = operation["responses"]
    assert isinstance(responses, dict)
    response = responses[str(status_code)]
    assert isinstance(response, dict)
    content = response["content"]
    assert isinstance(content, dict)
    schema_ref = content["application/json"]["schema"]["$ref"]
    assert isinstance(schema_ref, str)
    assert schema_ref.startswith("#/components/schemas/CommonResponse")

    component_name = schema_ref.rsplit("/", maxsplit=1)[-1]
    components = openapi_schema["components"]
    assert isinstance(components, dict)
    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    response_schema = schemas[component_name]
    assert isinstance(response_schema, dict)
    properties = response_schema["properties"]
    assert isinstance(properties, dict)
    assert {"success", "status", "data"} <= set(properties)


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
