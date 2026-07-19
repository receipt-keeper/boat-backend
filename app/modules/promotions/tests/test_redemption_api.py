import pytest

from app.modules.promotions.tests.api_helpers import (
    PROMOTION_ID,
    PUBLIC_BANNER_IMAGE_URL,
    PromotionCodeRedemptionCommandUseCaseStub,
    PromotionRedemptionCommandUseCaseStub,
    RedemptionOutcome,
    api_client,
    promotion_api_app,
)


async def test_create_promotion_redemption_returns_balance_and_benefit() -> None:
    # Given: 받을 수 있는 no-code OCR 프로모션이 있다.
    test_app = promotion_api_app(redemption_outcome=RedemptionOutcome.GRANTED)

    async with api_client(test_app) as test_client:
        # When: 프로모션 ID로 혜택 수령을 요청한다.
        response = await test_client.post(f"/api/v1/promotions/{PROMOTION_ID}/redemptions")

    # Then: 지급 결과와 변경된 잔액 표면을 받는다.
    data = response.json()["data"]
    assert response.status_code == 200
    _assert_public_promotion_fields(data)
    assert data["state"] == "alreadyRedeemed"
    assert data["promotionId"] == str(PROMOTION_ID)
    assert data["benefit"] == {"featureKey": "ocr", "amount": 3}
    assert data["redemption"] == {
        "remainingRedemptions": 7,
        "maxRedemptionsPerUser": None,
        "remainingRedemptionsForUser": None,
    }
    assert data["balance"] == {"totalGrantedCount": 8, "remainingCount": 6}
    assert data["bannerImage"] == {"imageUrl": PUBLIC_BANNER_IMAGE_URL}


async def test_create_promotion_code_redemption_uses_static_route() -> None:
    # Given: 사용할 수 있는 프로모션 코드가 있다.
    test_app = promotion_api_app(code_outcome=RedemptionOutcome.GRANTED)

    async with api_client(test_app) as test_client:
        # When: 정적 코드 리딤 path로 혜택 수령을 요청한다.
        response = await test_client.post(
            "/api/v1/promotions/redemptions",
            json={"code": "WELCOME2026"},
        )

    # Then: promotion_id 동적 path에 포획되지 않고 코드 리딤으로 처리된다.
    data = response.json()["data"]
    assert response.status_code == 200
    _assert_public_promotion_fields(data)
    assert data["promotionId"] == str(PROMOTION_ID)
    assert data["redemption"] == {
        "remainingRedemptions": 7,
        "maxRedemptionsPerUser": None,
        "remainingRedemptionsForUser": None,
    }
    assert data["bannerImage"] == {"imageUrl": PUBLIC_BANNER_IMAGE_URL}


async def test_create_promotion_redemption_forwards_idempotency_key_header() -> None:
    use_case = PromotionRedemptionCommandUseCaseStub(RedemptionOutcome.GRANTED)
    test_app = promotion_api_app(redemption_use_case=use_case)

    async with api_client(test_app) as test_client:
        response = await test_client.post(
            f"/api/v1/promotions/{PROMOTION_ID}/redemptions",
            headers={"Idempotency-Key": "attempt-1"},
        )

    assert response.status_code == 200
    assert len(use_case.commands) == 1
    assert use_case.commands[0].idempotency_key == "attempt-1"


async def test_create_promotion_code_redemption_forwards_idempotency_key_header() -> None:
    use_case = PromotionCodeRedemptionCommandUseCaseStub(RedemptionOutcome.GRANTED)
    test_app = promotion_api_app(code_use_case=use_case)

    async with api_client(test_app) as test_client:
        response = await test_client.post(
            "/api/v1/promotions/redemptions",
            json={"code": "WELCOME2026"},
            headers={"Idempotency-Key": "code-attempt-1"},
        )

    assert response.status_code == 200
    assert len(use_case.commands) == 1
    assert use_case.commands[0].idempotency_key == "code-attempt-1"


async def test_repeat_redemption_returns_already_redeemed_with_unchanged_balance() -> None:
    # Given: 같은 사용자가 이미 프로모션 혜택을 받은 상태다.
    test_app = promotion_api_app(redemption_outcome=RedemptionOutcome.ALREADY_REDEEMED)

    async with api_client(test_app) as test_client:
        # When: 같은 프로모션 수령을 다시 요청한다.
        response = await test_client.post(f"/api/v1/promotions/{PROMOTION_ID}/redemptions")

    # Then: 중복 지급 없이 기존 잔액 표면을 반환한다.
    data = response.json()["data"]
    assert response.status_code == 200
    assert data["state"] == "alreadyRedeemed"
    assert data["redemption"] == {
        "remainingRedemptions": 7,
        "maxRedemptionsPerUser": None,
        "remainingRedemptionsForUser": None,
    }
    assert data["balance"] == {"totalGrantedCount": 8, "remainingCount": 6}


@pytest.mark.parametrize(
    ("outcome", "path", "payload"),
    [
        (
            RedemptionOutcome.MISSING_PROMOTION,
            f"/api/v1/promotions/{PROMOTION_ID}/redemptions",
            None,
        ),
        (
            RedemptionOutcome.MISSING_CODE,
            "/api/v1/promotions/redemptions",
            {"code": "MISSING2026"},
        ),
    ],
)
async def test_missing_promotion_or_code_returns_404(
    outcome: RedemptionOutcome,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    # Given: 요청 대상 프로모션 또는 코드가 존재하지 않는다.
    test_app = promotion_api_app(redemption_outcome=outcome, code_outcome=outcome)

    async with api_client(test_app) as test_client:
        # When: 혜택 수령을 요청한다.
        response = await test_client.post(path, json=payload)

    # Then: missing 상태는 404로 매핑된다.
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("_scenario", "outcome"),
    [
        ("inactive", RedemptionOutcome.CONFLICT),
        ("expired", RedemptionOutcome.CONFLICT),
        ("exhausted", RedemptionOutcome.CONFLICT),
    ],
)
async def test_unavailable_redemption_returns_409(
    _scenario: str,
    outcome: RedemptionOutcome,
) -> None:
    # Given: 비활성, 만료, 또는 소진된 프로모션이다.
    test_app = promotion_api_app(redemption_outcome=outcome)

    async with api_client(test_app) as test_client:
        # When: 혜택 수령을 요청한다.
        response = await test_client.post(f"/api/v1/promotions/{PROMOTION_ID}/redemptions")

    # Then: 지급하지 않고 409로 매핑된다.
    assert response.status_code == 409


async def test_malformed_promotion_id_returns_422() -> None:
    # Given: 인증된 사용자가 있다.
    test_app = promotion_api_app()

    async with api_client(test_app) as test_client:
        # When: UUID가 아닌 promotion_id로 요청한다.
        response = await test_client.post("/api/v1/promotions/not-a-uuid/redemptions")

    # Then: path boundary에서 422로 거절된다.
    assert response.status_code == 422


@pytest.mark.parametrize("payload", [{"code": ""}, {"code": "bad code"}])
async def test_invalid_code_format_returns_422(payload: dict[str, str]) -> None:
    # Given: 인증된 사용자가 있다.
    test_app = promotion_api_app()

    async with api_client(test_app) as test_client:
        # When: 비어 있거나 형식이 잘못된 코드를 제출한다.
        response = await test_client.post("/api/v1/promotions/redemptions", json=payload)

    # Then: request body boundary에서 422로 거절된다.
    assert response.status_code == 422


def _assert_public_promotion_fields(data: dict[str, object]) -> None:
    assert set(data) == {
        "state",
        "promotionId",
        "kind",
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
