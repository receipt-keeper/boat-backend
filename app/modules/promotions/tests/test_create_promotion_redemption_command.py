from datetime import timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.domain.exceptions import NotFoundError
from app.modules.promotions.application.ports.credit_grant import (
    PromotionCreditGrant,
    PromotionCreditGrantResult,
)
from app.modules.promotions.domain.exceptions import PromotionRedemptionConflictError
from app.modules.promotions.domain.model import PromotionRedemptionStatus
from app.modules.promotions.infrastructure.persistence import orm
from app.modules.promotions.tests.helpers import (
    EXPIRED_PROMOTION_ID,
    NOW,
    PROMOTION_ID,
    PROMOTION_IDEMPOTENCY_KEY,
    USER_ID,
    FakePromotionCreditGrantPort,
    promotion_command,
    promotion_use_case,
    seed_promotion,
)


async def test_create_promotion_redemption_grants_credit_and_persists_redemption(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session)
        grant_port = FakePromotionCreditGrantPort(
            result=PromotionCreditGrantResult(
                credit_balance_after=8,
                credit_remaining_after=6,
            )
        )

        result = await promotion_use_case(session, grant_port).execute(promotion_command())

    async with postgres_session_factory() as session:
        redemption = await session.scalar(select(orm.PromotionRedemption))
        promotion = await session.get(orm.Promotion, PROMOTION_ID)

    assert result.status == PromotionRedemptionStatus.GRANTED
    assert result.already_redeemed is False
    assert result.credit_granted is True
    assert result.benefit_amount == 3
    assert result.remaining_redemptions == 9
    assert result.credit_balance_after == 8
    assert result.credit_remaining_after == 6
    assert redemption is not None
    assert redemption.idempotency_key == PROMOTION_IDEMPOTENCY_KEY
    assert redemption.redeemed_at == NOW
    assert promotion is not None
    assert promotion.times_redeemed == 1
    assert grant_port.grants == [
        PromotionCreditGrant(
            user_id=USER_ID,
            amount=3,
            redemption_id=result.redemption_id,
            idempotency_key=PROMOTION_IDEMPOTENCY_KEY,
        )
    ]


async def test_create_promotion_redemption_idempotent_retry_uses_current_response_surface(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session)
        grant_port = FakePromotionCreditGrantPort(
            result=PromotionCreditGrantResult(
                credit_balance_after=8,
                credit_remaining_after=6,
            )
        )
        use_case = promotion_use_case(session, grant_port)

        # Given: 최초 redeem 뒤 promotion benefit이 바뀐다.
        first = await use_case.execute(promotion_command())
        grant_call_count = len(grant_port.grants)
        await session.execute(
            update(orm.Promotion)
            .where(orm.Promotion.id == PROMOTION_ID)
            .values(benefit_amount=99, max_redemptions=1, active=False)
        )
        await session.commit()

        # When: 같은 idempotency key로 retry한다.
        second = await use_case.execute(promotion_command())

    assert second.redemption_id == first.redemption_id
    assert second.already_redeemed is True
    assert second.credit_granted is False
    assert second.benefit_amount == 99
    assert second.remaining_redemptions == 0
    assert second.credit_balance_after == first.credit_balance_after
    assert second.credit_remaining_after == first.credit_remaining_after
    assert len(grant_port.grants) == grant_call_count
    assert grant_port.grants[0].idempotency_key == PROMOTION_IDEMPOTENCY_KEY


@pytest.mark.parametrize(
    ("active", "starts_offset", "expires_offset", "max_redemptions", "times_redeemed"),
    [
        (False, -1, 1, 10, 0),
        (True, 1, 2, 10, 0),
        (True, -2, -1, 10, 0),
        (True, -1, 1, 1, 1),
    ],
)
async def test_create_promotion_redemption_rejects_unavailable_promotion_without_credit_call(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    active: bool,
    starts_offset: int,
    expires_offset: int,
    max_redemptions: int,
    times_redeemed: int,
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(
            session,
            active=active,
            starts_at=NOW + timedelta(days=starts_offset),
            expires_at=NOW + timedelta(days=expires_offset),
            max_redemptions=max_redemptions,
            times_redeemed=times_redeemed,
        )
        grant_port = FakePromotionCreditGrantPort()

        with pytest.raises(PromotionRedemptionConflictError):
            await promotion_use_case(session, grant_port).execute(promotion_command())

    assert grant_port.grants == []


async def test_create_promotion_redemption_raises_not_found_for_missing_promotion(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        grant_port = FakePromotionCreditGrantPort()

        with pytest.raises(NotFoundError):
            await promotion_use_case(session, grant_port).execute(promotion_command())

    assert grant_port.grants == []


async def test_expired_promotion_rejection_after_existing_redemption_does_not_call_credit_grant(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    grant_port = FakePromotionCreditGrantPort()
    async with postgres_session_factory() as session:
        await seed_promotion(session)
        first = await promotion_use_case(session, grant_port).execute(promotion_command())
        grant_port.grants.clear()

    async with postgres_session_factory() as session:
        await seed_promotion(session, promotion_id=EXPIRED_PROMOTION_ID, expires_at=NOW)
        with pytest.raises(PromotionRedemptionConflictError):
            await promotion_use_case(session, grant_port).execute(
                promotion_command(
                    promotion_id=EXPIRED_PROMOTION_ID,
                )
            )

    assert first.credit_granted is True
    assert grant_port.grants == []
