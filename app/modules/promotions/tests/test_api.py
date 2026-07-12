from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID

from app.main import create_app
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.query import (
    GetCurrentOcrCreditPromotionQuery,
)
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.result import (
    GetCurrentOcrCreditPromotionResult,
)
from app.modules.promotions.dependencies import (
    get_current_ocr_credit_promotion_query_use_case,
)
from app.modules.promotions.domain.model import PromotionContext
from app.modules.promotions.tests.api_helpers import (
    PUBLIC_BANNER_IMAGE_URL,
    TEST_SETTINGS,
    CurrentPromotionOutcome,
    api_client,
    promotion_api_app,
)

RECHARGE_PROMOTION_ID = UUID("00000000-0000-0000-0000-000000000209")

type OpenApiSchemaValue = (
    str | int | float | bool | None | list["OpenApiSchemaValue"] | dict[str, "OpenApiSchemaValue"]
)

OpenApiParameter = TypedDict(
    "OpenApiParameter",
    {
        "name": str,
        "in": str,
        "required": bool,
        "description": str,
        "schema": dict[str, OpenApiSchemaValue],
    },
)


async def test_get_promotions_route_returns_redeemable_app_state() -> None:
    # Given: 받을 수 있는 OCR 프로모션이 있는 인증 사용자가 있다.
    test_app = promotion_api_app(current_outcome=CurrentPromotionOutcome.REDEEMABLE)

    async with api_client(test_app) as test_client:
        # When: OCR 혜택 프로모션을 조회한다.
        response = await test_client.get("/api/v1/promotions?featureKey=ocr")

    # Then: 표시 문구 없이 상태/혜택/리딤/잔액 표면만 반환한다.
    body = response.json()
    assert response.status_code == 200
    _assert_public_promotion_fields(body["data"])
    assert body["data"] == {
        "state": "redeemable",
        "promotionId": "00000000-0000-0000-0000-000000000201",
        "benefit": {"featureKey": "ocr", "amount": 3},
        "redemption": {"remainingRedemptions": 10},
        "balance": None,
        "bannerImage": {"imageUrl": PUBLIC_BANNER_IMAGE_URL},
    }


async def test_get_promotions_route_returns_null_banner_image_without_image() -> None:
    # Given: 받을 수 있는 OCR 프로모션이 있지만 배너 이미지가 없다.
    test_app = promotion_api_app(current_outcome=CurrentPromotionOutcome.REDEEMABLE_WITHOUT_BANNER)

    async with api_client(test_app) as test_client:
        # When: OCR 혜택 프로모션을 조회한다.
        response = await test_client.get("/api/v1/promotions?featureKey=ocr")

    # Then: 배너 이미지는 null이고 서버 주도 문구 필드는 노출하지 않는다.
    body = response.json()
    assert response.status_code == 200
    _assert_public_promotion_fields(body["data"])
    assert body["data"]["bannerImage"] is None


async def test_get_promotions_route_returns_unavailable_without_display_fields() -> None:
    # Given: 현재 노출할 OCR 프로모션이 없는 인증 사용자가 있다.
    test_app = promotion_api_app(current_outcome=CurrentPromotionOutcome.UNAVAILABLE)

    async with api_client(test_app) as test_client:
        # When: OCR 혜택 프로모션을 조회한다.
        response = await test_client.get("/api/v1/promotions?featureKey=ocr")

    # Then: 앱이 숨김 상태로 처리할 수 있는 unavailable 응답을 받는다.
    assert response.status_code == 200
    assert response.json()["data"] == {
        "state": "unavailable",
        "promotionId": None,
        "benefit": None,
        "redemption": {"remainingRedemptions": None},
        "balance": None,
        "bannerImage": None,
    }


async def test_get_promotions_route_marks_already_redeemed() -> None:
    # Given: 이미 OCR 프로모션을 받은 인증 사용자가 있다.
    test_app = promotion_api_app(current_outcome=CurrentPromotionOutcome.ALREADY_REDEEMED)

    async with api_client(test_app) as test_client:
        # When: OCR 혜택 프로모션을 조회한다.
        response = await test_client.get("/api/v1/promotions?featureKey=ocr")

    # Then: 중복 수령 버튼을 막을 수 있는 alreadyRedeemed 상태를 받는다.
    assert response.status_code == 200
    assert response.json()["data"]["state"] == "alreadyRedeemed"
    assert response.json()["data"]["redemption"] == {"remainingRedemptions": 10}


async def test_get_promotions_route_passes_recharge_context_and_returns_amount_5() -> None:
    # Given: recharge context 조회를 기록하는 Promotion query use case가 있다.
    query_use_case = RechargePromotionQueryUseCaseStub()
    test_app = promotion_api_app()
    test_app.dependency_overrides[get_current_ocr_credit_promotion_query_use_case] = lambda: (
        query_use_case
    )

    async with api_client(test_app) as test_client:
        # When: 앱이 OCR 크레딧 충전용 프로모션을 조회한다.
        response = await test_client.get("/api/v1/promotions?featureKey=ocr&context=recharge")

    # Then: context가 application query로 전달되고 충전 혜택 수량 5가 반환된다.
    body = response.json()
    assert response.status_code == 200
    assert query_use_case.queries == [
        GetCurrentOcrCreditPromotionQuery(
            user_id=UUID("00000000-0000-0000-0000-000000000101"),
            context=PromotionContext.RECHARGE,
        )
    ]
    assert body["data"]["promotionId"] == str(RECHARGE_PROMOTION_ID)
    assert body["data"]["benefit"] == {"featureKey": "ocr", "amount": 5}


async def test_get_promotions_route_rejects_invalid_context() -> None:
    # Given: Promotion API가 있다.
    test_app = promotion_api_app()

    async with api_client(test_app) as test_client:
        # When: 허용되지 않은 context로 조회한다.
        response = await test_client.get("/api/v1/promotions?featureKey=ocr&context=bad")

    # Then: schema validation이 422를 반환한다.
    assert response.status_code == 422


async def test_get_promotions_route_rejects_signup_context() -> None:
    # Given: 가입 축하 캠페인을 public 조회로 노출하지 않는 Promotion API가 있다.
    test_app = promotion_api_app()

    async with api_client(test_app) as test_client:
        # When: 가입 축하 context로 공개 조회를 시도한다.
        response = await test_client.get("/api/v1/promotions?featureKey=ocr&context=signup")

    # Then: transport 경계에서 422로 거절한다.
    assert response.status_code == 422


def test_promotions_openapi_exposes_optional_context_query_parameter() -> None:
    # Given: 앱 공개 계약을 설명하는 OpenAPI 문서가 있다.
    test_app = create_app(TEST_SETTINGS)

    # When: 현재 앱의 promotions GET 파라미터를 조회한다.
    openapi_schema = test_app.openapi()
    parameters = openapi_schema["paths"]["/api/v1/promotions"]["get"]["parameters"]

    # Then: recharge enum을 가진 선택 context query parameter가 노출된다.
    feature_key_parameter = _parameter_by_name(parameters, "featureKey")
    feature_key_description = feature_key_parameter["description"]
    assert isinstance(feature_key_description, str)
    assert "featureKey=ocr&context=recharge" in feature_key_description
    context_parameter = _parameter_by_name(parameters, "context")
    assert context_parameter["in"] == "query"
    assert context_parameter["required"] is False
    schema = context_parameter["schema"]
    assert isinstance(schema, dict)
    any_of = schema["anyOf"]
    assert isinstance(any_of, list)
    recharge_schema = any_of[0]
    assert isinstance(recharge_schema, dict)
    assert recharge_schema["$ref"] == "#/components/schemas/PromotionQueryContext"
    assert openapi_schema["components"]["schemas"]["PromotionQueryContext"]["enum"] == ["recharge"]
    example = openapi_schema["components"]["schemas"]["PromotionResponse"]["examples"][0]
    assert isinstance(example, dict)
    assert example["benefit"] == {"featureKey": "ocr", "amount": 5}


def test_promotions_openapi_pins_public_paths_and_recharge_context_enum() -> None:
    # Given: 앱 공개 계약을 설명하는 OpenAPI 문서가 있다.
    test_app = create_app(TEST_SETTINGS)

    # When: promotions 공개 path와 context enum을 조회한다.
    openapi_schema = test_app.openapi()
    promotion_paths = [
        path for path in openapi_schema["paths"] if path.startswith("/api/v1/promotions")
    ]
    parameters = openapi_schema["paths"]["/api/v1/promotions"]["get"]["parameters"]
    context_schema = _parameter_by_name(parameters, "context")["schema"]

    # Then: recharge만 지원하며 기존 세 public path 외의 표면은 노출하지 않는다.
    assert promotion_paths == [
        "/api/v1/promotions",
        "/api/v1/promotions/redemptions",
        "/api/v1/promotions/{promotion_id}/redemptions",
    ]
    assert isinstance(context_schema, dict)
    any_of = context_schema["anyOf"]
    assert isinstance(any_of, list)
    context_reference = any_of[0]
    assert isinstance(context_reference, dict)
    context_reference_path = context_reference["$ref"]
    assert isinstance(context_reference_path, str)
    context_reference_name = context_reference_path.rsplit("/", maxsplit=1)[-1]
    assert context_reference_name == "PromotionQueryContext"
    assert openapi_schema["components"]["schemas"][context_reference_name]["enum"] == ["recharge"]


def test_promotions_openapi_documents_recharge_lookup_and_redemption_flow() -> None:
    # Given: 앱 공개 계약을 설명하는 OpenAPI 문서가 있다.
    test_app = create_app(TEST_SETTINGS)

    # When: 프로모션 조회/수령 operation 설명을 확인한다.
    openapi_schema = test_app.openapi()
    promotions_get = openapi_schema["paths"]["/api/v1/promotions"]["get"]
    promotion_redemption_post = openapi_schema["paths"][
        "/api/v1/promotions/{promotion_id}/redemptions"
    ]["post"]

    # Then: OCR 크레딧 충전 조회와 Idempotency-Key 수령 플로우가 문서화되어 있다.
    get_description = promotions_get["description"]
    redemption_description = promotion_redemption_post["description"]
    assert isinstance(get_description, str)
    assert isinstance(redemption_description, str)
    assert "/api/v1/promotions?featureKey=ocr&context=recharge" in get_description
    assert "state=redeemable" in get_description
    assert "Idempotency-Key" in redemption_description
    assert "크레딧" in get_description
    assert "token" not in get_description.casefold()
    assert "token" not in redemption_description.casefold()


async def test_promotions_routes_require_authentication() -> None:
    # Given: 보호된 Promotion API가 있다.
    test_app = create_app(TEST_SETTINGS)

    async with api_client(test_app) as test_client:
        # When: 인증 없이 Promotion API를 호출한다.
        response = await test_client.get("/api/v1/promotions?featureKey=ocr")

    # Then: 기존 bearer dependency가 401로 차단한다.
    assert response.status_code == 401


async def test_promotions_openapi_exposes_static_redemption_before_dynamic_path() -> None:
    # Given: 앱 공개 계약을 설명하는 OpenAPI 문서가 있다.
    test_app = create_app(TEST_SETTINGS)

    # When: 현재 앱의 OpenAPI path 목록을 조회한다.
    paths = list(test_app.openapi()["paths"])

    # Then: 코드 리딤 정적 path가 promotion_id 동적 path보다 먼저 선언된다.
    assert "/api/v1/promotions" in paths
    assert "/api/v1/promotions/redemptions" in paths
    assert "/api/v1/promotions/{promotion_id}/redemptions" in paths
    assert paths.index("/api/v1/promotions/redemptions") < paths.index(
        "/api/v1/promotions/{promotion_id}/redemptions"
    )


def _assert_public_promotion_fields(data: dict[str, object]) -> None:
    assert set(data) == {
        "state",
        "promotionId",
        "benefit",
        "redemption",
        "balance",
        "bannerImage",
    }
    assert not {
        "fileId",
        "title",
        "body",
        "ctaLabel",
        "surface",
        "metadata",
    }.intersection(data)


@dataclass(slots=True)  # noqa: RUF100  # noqa: MUTABLE_OK
class RechargePromotionQueryUseCaseStub:
    queries: list[GetCurrentOcrCreditPromotionQuery] = field(default_factory=list)

    async def execute(
        self,
        query: GetCurrentOcrCreditPromotionQuery,
    ) -> GetCurrentOcrCreditPromotionResult:
        self.queries.append(query)
        return GetCurrentOcrCreditPromotionResult(
            promotion_id=RECHARGE_PROMOTION_ID,
            name="월간 OCR 크레딧 충전 2026-07",
            benefit_amount=5,
            remaining_redemptions=None,
            starts_at=datetime(2026, 6, 30, 15, tzinfo=UTC),
            expires_at=datetime(2026, 7, 31, 15, tzinfo=UTC),
            already_redeemed=False,
            redemption_status=None,
            banner_image_url=None,
        )


def _parameter_by_name(parameters: list[OpenApiParameter], name: str) -> OpenApiParameter:
    for parameter in parameters:
        if parameter["name"] == name:
            return parameter
    raise AssertionError(f"{name} parameter not found")
