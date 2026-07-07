from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.unit_of_work import UnitOfWork
from app.core.db.outbox.orm import OutboxEvent
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.credits.infrastructure.persistence import orm as credits_orm
from app.modules.promotions.dependencies import get_promotion_unit_of_work
from app.modules.promotions.domain.exceptions import PromotionRedemptionConflictError
from app.modules.promotions.infrastructure.persistence import orm as promotions_orm
from app.modules.promotions.tests.api_helpers import api_client
from app.modules.promotions.tests.helpers import PROMOTION_ID, USER_ID, seed_promotion
from app.modules.promotions.tests.test_integration import _promotion_integration_app


async def test_promotion_redeem_rolls_back_credit_grant_when_outer_flow_fails_after_grant(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    test_app = _promotion_integration_app(postgres_session_factory)
    test_app.dependency_overrides[get_promotion_unit_of_work] = _failing_unit_of_work
    async with postgres_session_factory() as session:
        await seed_promotion(session, context="recharge", benefit_amount=5)

    async with api_client(test_app) as test_client:
        response = await test_client.post(f"/api/v1/promotions/{PROMOTION_ID}/redemptions")

    assert response.status_code == 409
    async with postgres_session_factory() as session:
        promotion = await session.get(promotions_orm.Promotion, PROMOTION_ID)
        redemptions = tuple(await session.scalars(select(promotions_orm.PromotionRedemption)))
        transactions = tuple(await session.scalars(select(credits_orm.CreditTransaction)))
        user_credit = await session.get(
            credits_orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )
        outbox_events = tuple(await session.scalars(select(OutboxEvent)))

    assert promotion is not None
    assert promotion.context == "recharge"
    assert promotion.benefit_amount == 5
    assert promotion.times_redeemed == 0
    assert redemptions == ()
    assert transactions == ()
    assert user_credit is None
    # commit 실패로 인한 rollback은 같은 세션에 insert된 outbox row도 원자적으로 소거한다.
    assert outbox_events == ()


async def _failing_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return FailingCommitUnitOfWork(delegate=SqlAlchemyUnitOfWork(session))


class FailingCommitUnitOfWork(UnitOfWork):
    def __init__(self, *, delegate: UnitOfWork) -> None:
        self._delegate = delegate

    async def commit(self) -> None:
        await self._delegate.rollback()
        raise PromotionRedemptionConflictError("테스트용 outer commit 실패입니다.")

    async def rollback(self) -> None:
        await self._delegate.rollback()
