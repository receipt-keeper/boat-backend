from app.main import create_app
from app.modules.promotions.tests.api_helpers import (
    TEST_SETTINGS,
    CurrentPromotionOutcome,
    api_client,
    promotion_api_app,
)


async def test_get_promotions_route_returns_redeemable_app_state() -> None:
    # Given: 받을 수 있는 OCR 프로모션이 있는 인증 사용자가 있다.
    test_app = promotion_api_app(current_outcome=CurrentPromotionOutcome.REDEEMABLE)

    async with api_client(test_app) as test_client:
        # When: OCR 혜택 프로모션을 조회한다.
        response = await test_client.get("/api/v1/promotions?benefitFeatureKey=ocr")

    # Then: 표시 문구 없이 상태/혜택/리딤/잔액 표면만 반환한다.
    body = response.json()
    assert response.status_code == 200
    assert set(body["data"]) == {"state", "promotionId", "benefit", "redemption", "balance"}
    assert body["data"] == {
        "state": "redeemable",
        "promotionId": "00000000-0000-0000-0000-000000000201",
        "benefit": {"featureKey": "ocr", "amount": 3},
        "redemption": {"remainingRedemptions": 10},
        "balance": None,
    }


async def test_get_promotions_route_returns_unavailable_without_display_fields() -> None:
    # Given: 현재 노출할 OCR 프로모션이 없는 인증 사용자가 있다.
    test_app = promotion_api_app(current_outcome=CurrentPromotionOutcome.UNAVAILABLE)

    async with api_client(test_app) as test_client:
        # When: OCR 혜택 프로모션을 조회한다.
        response = await test_client.get("/api/v1/promotions?benefitFeatureKey=ocr")

    # Then: 앱이 숨김 상태로 처리할 수 있는 unavailable 응답을 받는다.
    assert response.status_code == 200
    assert response.json()["data"] == {
        "state": "unavailable",
        "promotionId": None,
        "benefit": None,
        "redemption": {"remainingRedemptions": None},
        "balance": None,
    }


async def test_get_promotions_route_marks_already_redeemed() -> None:
    # Given: 이미 OCR 프로모션을 받은 인증 사용자가 있다.
    test_app = promotion_api_app(current_outcome=CurrentPromotionOutcome.ALREADY_REDEEMED)

    async with api_client(test_app) as test_client:
        # When: OCR 혜택 프로모션을 조회한다.
        response = await test_client.get("/api/v1/promotions?benefitFeatureKey=ocr")

    # Then: 중복 수령 버튼을 막을 수 있는 alreadyRedeemed 상태를 받는다.
    assert response.status_code == 200
    assert response.json()["data"]["state"] == "alreadyRedeemed"
    assert response.json()["data"]["redemption"] == {"remainingRedemptions": 10}


async def test_promotions_routes_require_authentication() -> None:
    # Given: 보호된 Promotion API가 있다.
    test_app = create_app(TEST_SETTINGS)

    async with api_client(test_app) as test_client:
        # When: 인증 없이 Promotion API를 호출한다.
        response = await test_client.get("/api/v1/promotions?benefitFeatureKey=ocr")

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
