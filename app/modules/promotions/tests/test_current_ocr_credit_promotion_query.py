from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.query import (
    GetCurrentOcrCreditPromotionQuery,
)
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.use_case import (
    GetCurrentOcrCreditPromotionQueryUseCase,
)
from app.modules.promotions.domain.model import PromotionRedemptionStatus
from app.modules.promotions.infrastructure.persistence.repository import (
    SqlAlchemyPromotionRepository,
)
from app.modules.promotions.tests.helpers import (
    BANNER_IMAGE_URL,
    NOW,
    PROMOTION_ID,
    USER_ID,
    FakePromotionCreditGrantPort,
    promotion_command,
    promotion_use_case,
    seed_promotion,
    seed_promotion_content,
)


async def test_get_current_ocr_credit_promotion_returns_user_status(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session)
        use_case = GetCurrentOcrCreditPromotionQueryUseCase(
            promotion_repository=SqlAlchemyPromotionRepository(session),
            clock=lambda: NOW,
        )

        result = await use_case.execute(GetCurrentOcrCreditPromotionQuery(user_id=USER_ID))

    assert result is not None
    assert result.promotion_id == PROMOTION_ID
    assert result.benefit_amount == 3
    assert result.banner_image_url is None
    assert result.already_redeemed is False
    assert result.redemption_status is None


async def test_get_current_ocr_credit_promotion_returns_banner_image_url(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session)
        await seed_promotion_content(session)
        use_case = GetCurrentOcrCreditPromotionQueryUseCase(
            promotion_repository=SqlAlchemyPromotionRepository(session),
            clock=lambda: NOW,
        )

        result = await use_case.execute(GetCurrentOcrCreditPromotionQuery(user_id=USER_ID))

    assert result is not None
    assert result.promotion_id == PROMOTION_ID
    assert result.banner_image_url == BANNER_IMAGE_URL


async def test_get_current_ocr_credit_promotion_marks_already_redeemed_for_user(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session)
        await promotion_use_case(session, FakePromotionCreditGrantPort()).execute(
            promotion_command()
        )
        use_case = GetCurrentOcrCreditPromotionQueryUseCase(
            promotion_repository=SqlAlchemyPromotionRepository(session),
            clock=lambda: NOW,
        )

        result = await use_case.execute(GetCurrentOcrCreditPromotionQuery(user_id=USER_ID))

    assert result is not None
    assert result.promotion_id == PROMOTION_ID
    assert result.banner_image_url is None
    assert result.already_redeemed is True
    assert result.redemption_status == PromotionRedemptionStatus.GRANTED
