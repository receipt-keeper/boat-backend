from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.unit_of_work import UnitOfWork
from app.core.db.base import Base
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.promotions.application.commands.redeem_signup_promotion.use_case import (
    RedeemSignupPromotionCommandUseCase,
)
from app.modules.promotions.dependencies import (
    build_redeem_signup_promotion_command_use_case,
)
from app.modules.promotions.domain.exceptions import PromotionRedemptionConflictError
from app.modules.promotions.infrastructure.persistence import orm as promotions_orm


def signup_use_case(session: AsyncSession) -> RedeemSignupPromotionCommandUseCase:
    return build_redeem_signup_promotion_command_use_case(session, SqlAlchemyUnitOfWork(session))


async def seed_active_signup_campaign(
    session: AsyncSession,
    *,
    benefit_amount: int = 5,
) -> UUID:
    now = datetime.now(UTC)
    return await seed_signup_campaign(
        session,
        active=True,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=1),
        max_redemptions=None,
        times_redeemed=0,
        benefit_amount=benefit_amount,
    )


async def seed_signup_campaign(
    session: AsyncSession,
    *,
    active: bool,
    starts_at: datetime,
    expires_at: datetime,
    max_redemptions: int | None,
    times_redeemed: int,
    benefit_amount: int = 5,
) -> UUID:
    promotion_id = uuid4()
    session.add(
        promotions_orm.Promotion(
            id=promotion_id,
            name="신규 가입 OCR 크레딧",
            active=active,
            starts_at=starts_at,
            expires_at=expires_at,
            max_redemptions=max_redemptions,
            times_redeemed=times_redeemed,
            max_redemptions_per_user=1,
            benefit_feature_key="ocr",
            context="signup",
            benefit_amount=benefit_amount,
        )
    )
    await session.commit()
    return promotion_id


async def count_rows(session: AsyncSession, model: type[Base]) -> int:
    return (await session.scalar(select(func.count()).select_from(model))) or 0


class FailingCommitUnitOfWork(UnitOfWork):
    def __init__(self, *, delegate: UnitOfWork) -> None:
        self._delegate = delegate

    async def commit(self) -> None:
        await self._delegate.rollback()
        raise PromotionRedemptionConflictError("테스트용 outer commit 실패입니다.")

    async def rollback(self) -> None:
        await self._delegate.rollback()
