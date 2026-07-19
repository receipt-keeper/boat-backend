from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.query import (
    GetCurrentOcrCreditPromotionQuery,
)
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.use_case import (
    GetCurrentOcrCreditPromotionQueryUseCase,
)
from app.modules.promotions.domain.model import (
    PromotionContext,
    PromotionKind,
    PromotionRedemptionStatus,
)
from app.modules.promotions.infrastructure.persistence import orm
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

RECHARGE_PROMOTION_ID = UUID("00000000-0000-0000-0000-000000000209")


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
    assert result.kind is None
    assert result.max_redemptions_per_user == 1
    assert result.remaining_redemptions_for_user == 1
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


async def test_get_current_ocr_credit_promotion_stays_redeemable_until_user_limit(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session, max_redemptions_per_user=2)
        await promotion_use_case(session, FakePromotionCreditGrantPort()).execute(
            promotion_command(idempotency_key="attempt-1")
        )
        use_case = GetCurrentOcrCreditPromotionQueryUseCase(
            promotion_repository=SqlAlchemyPromotionRepository(session),
            clock=lambda: NOW,
        )

        result = await use_case.execute(GetCurrentOcrCreditPromotionQuery(user_id=USER_ID))

    assert result is not None
    assert result.promotion_id == PROMOTION_ID
    assert result.already_redeemed is False
    assert result.redemption_status is None


async def test_get_current_ocr_credit_promotion_returns_recharge_context_when_newer_general_exists(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_ocr_promotion(session, promotion_id=PROMOTION_ID, starts_at=NOW, amount=3)
        await _seed_ocr_promotion(
            session,
            promotion_id=RECHARGE_PROMOTION_ID,
            starts_at=NOW.replace(hour=10),
            context=PromotionContext.RECHARGE.value,
            amount=5,
        )
        use_case = GetCurrentOcrCreditPromotionQueryUseCase(
            promotion_repository=SqlAlchemyPromotionRepository(session),
            clock=lambda: NOW,
        )

        result = await use_case.execute(
            GetCurrentOcrCreditPromotionQuery(
                user_id=USER_ID,
                context=PromotionContext.RECHARGE,
            )
        )

    assert result is not None
    assert result.promotion_id == RECHARGE_PROMOTION_ID
    assert result.benefit_amount == 5


async def test_rewarded_ad_query_counts_only_current_kst_day(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    current_day_start = datetime(2026, 7, 2, 15, 0, tzinfo=NOW.tzinfo)
    async with postgres_session_factory() as session:
        await seed_promotion(
            session,
            context=PromotionContext.RECHARGE.value,
            kind=PromotionKind.REWARDED_AD.value,
            max_redemptions_per_user=2,
        )
        session.add_all(
            [
                _granted_redemption(
                    redemption_id=UUID("00000000-0000-0000-0000-000000000601"),
                    redeemed_at=current_day_start - timedelta(seconds=1),
                    idempotency_key="previous-day",
                ),
                _granted_redemption(
                    redemption_id=UUID("00000000-0000-0000-0000-000000000602"),
                    redeemed_at=current_day_start,
                    idempotency_key="current-day",
                ),
            ]
        )
        await session.commit()
        use_case = GetCurrentOcrCreditPromotionQueryUseCase(
            promotion_repository=SqlAlchemyPromotionRepository(session),
            clock=lambda: NOW,
        )

        result = await use_case.execute(
            GetCurrentOcrCreditPromotionQuery(
                user_id=USER_ID,
                context=PromotionContext.RECHARGE,
                kind=PromotionKind.REWARDED_AD,
            )
        )

    assert result is not None
    assert result.kind == PromotionKind.REWARDED_AD
    assert result.max_redemptions_per_user == 2
    assert result.remaining_redemptions_for_user == 1
    assert result.already_redeemed is False


async def test_get_current_ocr_credit_promotion_preserves_legacy_lookup_when_context_omitted(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_ocr_promotion(
            session,
            promotion_id=PROMOTION_ID,
            starts_at=NOW.replace(hour=8),
            amount=3,
        )
        await _seed_ocr_promotion(
            session,
            promotion_id=RECHARGE_PROMOTION_ID,
            starts_at=NOW.replace(hour=10),
            context=PromotionContext.RECHARGE.value,
            amount=5,
        )
        use_case = GetCurrentOcrCreditPromotionQueryUseCase(
            promotion_repository=SqlAlchemyPromotionRepository(session),
            clock=lambda: NOW,
        )

        result = await use_case.execute(GetCurrentOcrCreditPromotionQuery(user_id=USER_ID))

    assert result is not None
    assert result.promotion_id == PROMOTION_ID
    assert result.benefit_amount == 3


async def _seed_ocr_promotion(
    session: AsyncSession,
    *,
    promotion_id: UUID,
    starts_at: datetime,
    context: str | None = None,
    amount: int,
) -> None:
    session.add(
        orm.Promotion(
            id=promotion_id,
            name="OCR credit promotion",
            active=True,
            starts_at=starts_at,
            expires_at=NOW.replace(day=4),
            max_redemptions=10,
            times_redeemed=0,
            max_redemptions_per_user=1,
            benefit_feature_key="ocr",
            context=context,
            benefit_amount=amount,
        )
    )
    await session.commit()


def _granted_redemption(
    *,
    redemption_id: UUID,
    redeemed_at: datetime,
    idempotency_key: str,
) -> orm.PromotionRedemption:
    return orm.PromotionRedemption(
        id=redemption_id,
        promotion_id=PROMOTION_ID,
        promotion_code_id=None,
        user_id=USER_ID,
        status=PromotionRedemptionStatus.GRANTED.value,
        idempotency_key=idempotency_key,
        redeemed_at=redeemed_at,
    )
