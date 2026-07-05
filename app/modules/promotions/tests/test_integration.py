from uuid import UUID

from fastapi import FastAPI, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.http.auth import set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.main import create_app
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.credits.domain import CreditReason, CreditSourceType
from app.modules.credits.infrastructure.persistence import orm as credits_orm
from app.modules.promotions.infrastructure.persistence import orm as promotions_orm
from app.modules.promotions.tests.api_helpers import (
    PUBLIC_BANNER_IMAGE_URL,
    TEST_CREDENTIALS_ID,
    TEST_SESSION_ID,
    TEST_SETTINGS,
    api_client,
)
from app.modules.promotions.tests.helpers import (
    CODE_ID,
    CODE_IDEMPOTENCY_KEY,
    NOW,
    PROMOTION_ID,
    PROMOTION_IDEMPOTENCY_KEY,
    USER_ID,
    seed_promotion,
    seed_promotion_content,
)

CODE_PROMOTION_ID = UUID("00000000-0000-0000-0000-000000000203")


async def test_no_code_promotion_redemption_grants_credit_once_through_real_wiring(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 실제 Promotion API dependency graph와 받을 수 있는 no-code 프로모션이 있다.
    test_app = _promotion_integration_app(postgres_session_factory)
    async with postgres_session_factory() as session:
        await seed_promotion(session, expires_at=None)
        await seed_promotion_content(session)

    async with api_client(test_app) as test_client:
        # When: 같은 프로모션 혜택 수령을 두 번 요청한다.
        first_response = await test_client.post(f"/api/v1/promotions/{PROMOTION_ID}/redemptions")
        second_response = await test_client.post(f"/api/v1/promotions/{PROMOTION_ID}/redemptions")

    # Then: Promotion redemption과 Credits ledger가 한 번만 저장된다.
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["data"]["balance"] == {
        "totalGrantedCount": 3,
        "remainingCount": 3,
    }
    assert second_response.json()["data"]["balance"] == {
        "totalGrantedCount": 3,
        "remainingCount": 3,
    }
    assert first_response.json()["data"]["bannerImage"] == {
        "imageUrl": PUBLIC_BANNER_IMAGE_URL,
    }
    assert second_response.json()["data"]["bannerImage"] == {
        "imageUrl": PUBLIC_BANNER_IMAGE_URL,
    }

    async with postgres_session_factory() as session:
        promotion = await session.get(promotions_orm.Promotion, PROMOTION_ID)
        redemption = await _single_redemption(session, promotion_id=PROMOTION_ID)
        transaction = await _single_credit_transaction(session)
        user_credit = await session.get(
            credits_orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )

    assert promotion is not None
    assert promotion.times_redeemed == 1
    assert redemption.promotion_code_id is None
    assert transaction.reason == CreditReason.EVENT_OCR_ALLOWANCE.value
    assert transaction.source_type == CreditSourceType.PROMOTION_REDEMPTION.value
    assert transaction.source_id == redemption.id
    assert transaction.idempotency_key == PROMOTION_IDEMPOTENCY_KEY
    assert user_credit is not None
    assert user_credit.total_granted_count == 3
    assert user_credit.remaining_count == 3


async def test_code_promotion_redemption_grants_credit_once_through_real_wiring(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 실제 Promotion API dependency graph와 받을 수 있는 code 프로모션이 있다.
    test_app = _promotion_integration_app(postgres_session_factory)
    async with postgres_session_factory() as session:
        await _seed_code_promotion(session)
        await seed_promotion_content(session, promotion_id=CODE_PROMOTION_ID)

    async with api_client(test_app) as test_client:
        # When: 같은 프로모션 코드 혜택 수령을 두 번 요청한다.
        first_response = await test_client.post(
            "/api/v1/promotions/redemptions",
            json={"code": "WELCOME2026"},
        )
        second_response = await test_client.post(
            "/api/v1/promotions/redemptions",
            json={"code": "WELCOME2026"},
        )

    # Then: Promotion code 사용량과 Credits ledger가 한 번만 저장된다.
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["data"]["balance"] == {
        "totalGrantedCount": 3,
        "remainingCount": 3,
    }
    assert second_response.json()["data"]["balance"] == {
        "totalGrantedCount": 3,
        "remainingCount": 3,
    }
    assert first_response.json()["data"]["bannerImage"] == {
        "imageUrl": PUBLIC_BANNER_IMAGE_URL,
    }
    assert second_response.json()["data"]["bannerImage"] == {
        "imageUrl": PUBLIC_BANNER_IMAGE_URL,
    }

    async with postgres_session_factory() as session:
        promotion = await session.get(promotions_orm.Promotion, CODE_PROMOTION_ID)
        code = await session.get(promotions_orm.PromotionCode, CODE_ID)
        redemption = await _single_redemption(session, promotion_id=CODE_PROMOTION_ID)
        transaction = await _single_credit_transaction(session)
        user_credit = await session.get(
            credits_orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )

    assert promotion is not None
    assert promotion.times_redeemed == 1
    assert code is not None
    assert code.times_redeemed == 1
    assert redemption.promotion_code_id == CODE_ID
    assert transaction.reason == CreditReason.EVENT_OCR_ALLOWANCE.value
    assert transaction.source_type == CreditSourceType.PROMOTION_REDEMPTION.value
    assert transaction.source_id == redemption.id
    assert transaction.idempotency_key == CODE_IDEMPOTENCY_KEY
    assert user_credit is not None
    assert user_credit.total_granted_count == 3
    assert user_credit.remaining_count == 3


def _promotion_integration_app(
    session_factory: async_sessionmaker[AsyncSession],
) -> FastAPI:
    test_app = create_app(TEST_SETTINGS)
    test_app.state.session_factory = session_factory
    test_app.dependency_overrides[authenticate_current_principal] = _authenticate_test_principal
    return test_app


async def _authenticate_test_principal(request: Request) -> AuthenticatedPrincipal:
    principal = AuthenticatedPrincipal(
        user_id=USER_ID,
        credentials_id=TEST_CREDENTIALS_ID,
        session_id=TEST_SESSION_ID,
        role="user",
    )
    set_current_principal(request, principal)
    return principal


async def _seed_code_promotion(session: AsyncSession) -> None:
    session.add(
        promotions_orm.Promotion(
            id=CODE_PROMOTION_ID,
            name="OCR code promotion",
            active=True,
            starts_at=NOW,
            expires_at=None,
            max_redemptions=10,
            times_redeemed=0,
            max_redemptions_per_user=1,
            benefit_feature_key="ocr",
            benefit_amount=3,
        )
    )
    session.add(
        promotions_orm.PromotionCode(
            id=CODE_ID,
            promotion_id=CODE_PROMOTION_ID,
            code="WELCOME2026",
            active=True,
            starts_at=NOW,
            expires_at=None,
            max_redemptions=10,
            times_redeemed=0,
        )
    )
    await session.commit()


async def _single_redemption(
    session: AsyncSession,
    *,
    promotion_id: UUID,
) -> promotions_orm.PromotionRedemption:
    redemptions = tuple(
        await session.scalars(
            select(promotions_orm.PromotionRedemption).where(
                promotions_orm.PromotionRedemption.user_id == USER_ID,
                promotions_orm.PromotionRedemption.promotion_id == promotion_id,
            )
        )
    )
    assert len(redemptions) == 1
    return redemptions[0]


async def _single_credit_transaction(
    session: AsyncSession,
) -> credits_orm.CreditTransaction:
    transactions = tuple(
        await session.scalars(
            select(credits_orm.CreditTransaction).where(
                credits_orm.CreditTransaction.user_id == USER_ID,
            )
        )
    )
    assert len(transactions) == 1
    return transactions[0]
