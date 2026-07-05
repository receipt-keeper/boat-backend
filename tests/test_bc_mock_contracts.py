import json

from httpx import ASGITransport, AsyncClient

from app.main import create_app
from tests.support.credits_usage_contract import (
    EMPTY_CREDITS_USER_ID,
    EXPECTED_PUBLIC_PATHS,
    FORBIDDEN_ME_FIELDS,
    FORBIDDEN_OPENAPI_PUBLIC_TERMS,
    FORBIDDEN_PUBLIC_PATHS,
    SEEDED_CREDITS_USER_ID,
    TEST_SETTINGS,
    create_credits_usage_contract_app,
)

type JsonObject = dict[str, JsonValue]
type JsonValue = JsonObject | list[JsonValue] | str | int | float | bool | None


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


async def test_promotion_content_and_code_resources_are_absent_from_openapi() -> None:
    # Given: 앱 공개 계약을 설명하는 OpenAPI 문서가 있다.
    test_app = create_app(TEST_SETTINGS)

    # When: 현재 앱의 OpenAPI path 목록을 조회한다.
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as test_client:
        response = await test_client.get("/openapi.json")

    paths = set(response.json()["paths"])

    # Then: 프로모션은 기존 app-facing route만 공개하고 content/code resource는 공개하지 않는다.
    assert response.status_code == 200
    assert not {
        path
        for path in paths
        if path.startswith("/api/v1/promotion-contents")
        or path.startswith("/api/v1/promotion-codes")
    }


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


def test_credits_usage_openapi_stays_read_only() -> None:
    # Given: 앱 공개 계약을 설명하는 OpenAPI 문서가 있다.
    schema = create_app(TEST_SETTINGS).openapi()
    paths = schema["paths"]

    # When: 크레딧/사용량 공개 path의 HTTP method를 확인한다.
    credits_methods = set(paths["/api/v1/credits"])
    credit_transaction_methods = set(paths["/api/v1/credits/transactions"])
    usage_methods = set(paths["/api/v1/usage"])

    # Then: 조회성 API만 공개하고 충전/지급 POST 경로는 공개하지 않는다.
    assert credits_methods == {"get"}
    assert credit_transaction_methods == {"get"}
    assert usage_methods == {"get"}
    assert not {
        path
        for path in paths
        if path.startswith("/api/v1/credits/")
        and any(term in path for term in ("free-recharge", "grant", "recharge"))
    }


async def test_credits_empty_user_reads_zero_snapshot() -> None:
    # Given: OCR 크레딧 snapshot과 내역이 아직 없는 인증 사용자가 있다.
    test_app = create_credits_usage_contract_app(EMPTY_CREDITS_USER_ID)

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        # When: 크레딧 계약 API를 조회한다.
        credits_response = await test_client.get("/api/v1/credits")
        transactions_response = await test_client.get("/api/v1/credits/transactions")

    credits_body = credits_response.json()
    transactions_body = transactions_response.json()

    # Then: 빈 사용자 snapshot은 0/0/0이며 내역 page는 비어 있다.
    assert credits_response.status_code == 200
    assert credits_body["data"] == {
        "totalGrantedCount": 0,
        "usedCount": 0,
        "remainingCount": 0,
    }
    assert transactions_response.status_code == 200
    assert transactions_body["data"]["pagination"] == {
        "nextCursor": None,
        "hasNext": False,
        "limit": 20,
        "totalCount": 0,
    }
    assert transactions_body["data"]["transactions"] == []


async def test_credits_seeded_user_reads_persisted_cursor_page() -> None:
    # Given: OCR 크레딧 snapshot과 세 건의 지급/사용 내역이 저장된 인증 사용자가 있다.
    test_app = create_credits_usage_contract_app(SEEDED_CREDITS_USER_ID)

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        # When: 잔액, 첫 내역 page, 다음 내역 page를 조회한다.
        credits_response = await test_client.get("/api/v1/credits")
        transactions_response = await test_client.get("/api/v1/credits/transactions?limit=2")
        first_page = transactions_response.json()["data"]
        next_cursor = first_page["pagination"]["nextCursor"]
        next_transactions_response = await test_client.get(
            f"/api/v1/credits/transactions?limit=1&cursor={next_cursor}"
        )

    credits_body = credits_response.json()
    next_transactions_body = next_transactions_response.json()

    # Then: 잔액은 저장된 snapshot에서 반환된다.
    assert credits_response.status_code == 200
    assert credits_body["data"] == {
        "totalGrantedCount": 15,
        "usedCount": 5,
        "remainingCount": 10,
    }
    assert transactions_response.status_code == 200
    assert first_page["transactions"] == [
        {
            "reason": "monthlyOcrAllowance",
            "action": "grant",
            "amount": 12,
            "createdAt": "2026-06-29T09:00:00+00:00",
        },
        {
            "reason": "eventOcrAllowance",
            "action": "grant",
            "amount": 3,
            "createdAt": "2026-06-29T09:03:00+00:00",
        },
    ]
    assert first_page["pagination"]["hasNext"] is True
    assert first_page["pagination"]["limit"] == 2
    assert first_page["pagination"]["totalCount"] == 3
    assert isinstance(first_page["pagination"]["nextCursor"], str)
    assert first_page["pagination"]["nextCursor"] != ""
    assert next_transactions_response.status_code == 200
    assert next_transactions_body["data"] == {
        "transactions": [
            {
                "reason": "ocrUsage",
                "action": "use",
                "amount": 5,
                "createdAt": "2026-06-29T09:05:00+00:00",
            }
        ],
        "pagination": {
            "nextCursor": None,
            "hasNext": False,
            "limit": 1,
            "totalCount": 3,
        },
    }


async def test_usage_empty_user_cannot_analyze_receipt() -> None:
    # Given: OCR 크레딧 snapshot이 아직 없는 인증 사용자가 있다.
    test_app = create_credits_usage_contract_app(EMPTY_CREDITS_USER_ID)

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        # When: 사용량 계약 API를 조회한다.
        response = await test_client.get("/api/v1/usage")

    body = response.json()

    # Then: OCR 사용 가능 여부는 남은 크레딧 0에서 false로 파생된다.
    assert response.status_code == 200
    assert body["data"] == {
        "ocr": {
            "remainingCount": 0,
            "canAnalyze": False,
        }
    }


async def test_usage_seeded_user_can_analyze_receipt() -> None:
    # Given: 남은 크레딧이 저장된 인증 사용자가 있다.
    test_app = create_credits_usage_contract_app(SEEDED_CREDITS_USER_ID)

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        # When: 사용량 계약 API를 조회한다.
        response = await test_client.get("/api/v1/usage")

    body = response.json()

    # Then: OCR 사용 가능 여부는 남은 크레딧이 0보다 크면 true로 파생된다.
    assert response.status_code == 200
    assert body["data"] == {
        "ocr": {
            "remainingCount": 10,
            "canAnalyze": True,
        }
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
    openapi_schema: JsonObject,
    operation: JsonObject,
    status_code: int,
) -> None:
    responses = operation["responses"]
    assert isinstance(responses, dict)
    response = responses[str(status_code)]
    assert isinstance(response, dict)
    content = response["content"]
    assert isinstance(content, dict)
    media_type = content["application/json"]
    assert isinstance(media_type, dict)
    media_schema = media_type["schema"]
    assert isinstance(media_schema, dict)
    schema_ref = media_schema["$ref"]
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
    test_app = create_credits_usage_contract_app()

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
