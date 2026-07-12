from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import anyio
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.outbox.orm import OutboxEvent
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.exceptions import ValidationError
from app.modules.credits.infrastructure.persistence import orm as credits_orm
from app.modules.promotions.application.commands.redeem_signup_promotion.command import (
    RedeemSignupPromotionCommand,
)
from app.modules.promotions.dependencies import (
    build_redeem_signup_promotion_command_use_case,
)
from app.modules.promotions.domain.exceptions import PromotionRedemptionConflictError
from app.modules.promotions.infrastructure.persistence import orm as promotions_orm
from app.modules.promotions.tests.signup_promotion_test_support import (
    FailingCommitUnitOfWork,
    count_rows,
    seed_active_signup_campaign,
    seed_signup_campaign,
    signup_use_case,
)

_BENEFICIARY_KEY = "v1:signup-beneficiary"
_PARAMETRIZE_NOW = datetime.now(UTC)


def test_redeem_signup_promotion_rejects_malformed_beneficiary_key() -> None:
    # Given: 공백뿐인 beneficiary key가 전달된다.
    # When: 내부 signup command를 만든다.
    # Then: 저장소 접근 전에 typed validation error로 차단한다.
    with pytest.raises(ValidationError):
        RedeemSignupPromotionCommand(user_id=uuid4(), beneficiary_key=" ")


async def test_redeem_signup_promotion_grants_active_campaign_amount_with_real_database(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 지급량 5의 활성 signup campaign이 있다.
    user_id = uuid4()
    async with postgres_session_factory() as session:
        promotion_id = await seed_active_signup_campaign(session, benefit_amount=5)
        use_case = signup_use_case(session)

        # When: 신규 가입 내부 flow가 opaque beneficiary key로 수령한다.
        result = await use_case.execute(
            RedeemSignupPromotionCommand(user_id=user_id, beneficiary_key=_BENEFICIARY_KEY)
        )

    # Then: public transport 정보 없이 지급 여부만 반환하고, 실제 ledger/outbox가 한 번씩 남는다.
    assert result.granted is True
    async with postgres_session_factory() as session:
        promotion = await session.get(promotions_orm.Promotion, promotion_id)
        redemptions = tuple(await session.scalars(select(promotions_orm.PromotionRedemption)))
        transactions = tuple(await session.scalars(select(credits_orm.CreditTransaction)))
        user_credit = await session.get(
            credits_orm.UserCredit,
            {"user_id": user_id, "feature_key": "ocr"},
        )
        event_types = tuple(await session.scalars(select(OutboxEvent.event_type)))

    assert promotion is not None
    assert promotion.times_redeemed == 1
    assert len(redemptions) == 1
    assert redemptions[0].beneficiary_key == _BENEFICIARY_KEY
    assert len(transactions) == 1
    assert transactions[0].amount == 5
    assert user_credit is not None
    assert (user_credit.total_granted_count, user_credit.remaining_count) == (5, 5)
    assert Counter(event_types) == Counter({"PromotionRedemptionGranted": 1, "CreditGranted": 1})


async def test_redeem_signup_promotion_returns_not_granted_without_current_campaign(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 활성 signup campaign이 없다.
    user_id = uuid4()
    async with postgres_session_factory() as session:
        # When: 내부 signup flow가 실행된다.
        result = await signup_use_case(session).execute(
            RedeemSignupPromotionCommand(user_id=user_id, beneficiary_key=_BENEFICIARY_KEY)
        )

    # Then: 가입 자체를 실패시키지 않고 영속 side effect 없이 no-op이다.
    assert result.granted is False
    async with postgres_session_factory() as session:
        assert await count_rows(session, promotions_orm.PromotionRedemption) == 0
        assert await count_rows(session, credits_orm.CreditTransaction) == 0


@pytest.mark.parametrize(
    ("active", "starts_at", "expires_at", "max_redemptions", "times_redeemed"),
    [
        (
            False,
            _PARAMETRIZE_NOW - timedelta(days=1),
            _PARAMETRIZE_NOW + timedelta(days=1),
            None,
            0,
        ),
        (
            True,
            _PARAMETRIZE_NOW + timedelta(days=1),
            _PARAMETRIZE_NOW + timedelta(days=2),
            None,
            0,
        ),
        (
            True,
            _PARAMETRIZE_NOW - timedelta(days=2),
            _PARAMETRIZE_NOW - timedelta(days=1),
            None,
            0,
        ),
        (
            True,
            _PARAMETRIZE_NOW - timedelta(days=1),
            _PARAMETRIZE_NOW + timedelta(days=1),
            1,
            1,
        ),
    ],
)
async def test_redeem_signup_promotion_returns_not_granted_when_campaign_is_unavailable(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    active: bool,
    starts_at: datetime,
    expires_at: datetime,
    max_redemptions: int | None,
    times_redeemed: int,
) -> None:
    # Given: inactive, not-started, expired 또는 global cap exhausted signup campaign이 있다.
    async with postgres_session_factory() as session:
        await seed_signup_campaign(
            session,
            active=active,
            starts_at=starts_at,
            expires_at=expires_at,
            max_redemptions=max_redemptions,
            times_redeemed=times_redeemed,
        )

        # When: 신규 가입 자동 수령을 시도한다.
        result = await signup_use_case(session).execute(
            RedeemSignupPromotionCommand(user_id=uuid4(), beneficiary_key=_BENEFICIARY_KEY)
        )

    # Then: campaign 상태는 signup failure가 아니라 no-op으로 처리한다.
    assert result.granted is False


async def test_redeem_signup_promotion_keeps_old_user_beneficiary_redemption_as_no_op(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 탈퇴 전 다른 user_id가 같은 beneficiary로 이미 지급받았다.
    old_user_id = uuid4()
    new_user_id = uuid4()
    async with postgres_session_factory() as session:
        promotion_id = await seed_active_signup_campaign(session)
        session.add(
            promotions_orm.PromotionRedemption(
                id=uuid4(),
                promotion_id=promotion_id,
                promotion_code_id=None,
                user_id=old_user_id,
                beneficiary_key=_BENEFICIARY_KEY,
                status="granted",
                idempotency_key="legacy-signup-beneficiary-redemption",
                failure_reason=None,
                redeemed_at=datetime.now(UTC),
            )
        )
        await session.commit()

        # When: 재가입으로 새 user_id가 생성돼도 같은 beneficiary를 전달한다.
        result = await signup_use_case(session).execute(
            RedeemSignupPromotionCommand(user_id=new_user_id, beneficiary_key=_BENEFICIARY_KEY)
        )

    # Then: 기존 잔액 조회나 새 credit grant 없이 no-op이다.
    assert result.granted is False
    async with postgres_session_factory() as session:
        assert await count_rows(session, promotions_orm.PromotionRedemption) == 1
        assert await count_rows(session, credits_orm.CreditTransaction) == 0


async def test_redeem_signup_promotion_concurrently_grants_same_beneficiary_once(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 두 가입 request가 같은 stable beneficiary를 동시에 처리한다.
    user_ids = (uuid4(), uuid4())
    async with postgres_session_factory() as session:
        await seed_active_signup_campaign(session, benefit_amount=5)

    start = anyio.Event()
    results: list[tuple[UUID, bool]] = []

    async def redeem_once(user_id: UUID) -> None:
        await start.wait()
        async with postgres_session_factory() as session:
            result = await signup_use_case(session).execute(
                RedeemSignupPromotionCommand(user_id=user_id, beneficiary_key=_BENEFICIARY_KEY)
            )
        results.append((user_id, result.granted))

    # When: 실제 PostgreSQL session 두 개로 동시에 실행한다.
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(redeem_once, user_ids[0])
        task_group.start_soon(redeem_once, user_ids[1])
        start.set()

    # Then: 수혜자 기준으로 정확히 한 번만 redemption, credit transaction, event 쌍이 남는다.
    assert sorted(granted for _, granted in results) == [False, True]
    granted_user_id = next(user_id for user_id, granted in results if granted)
    async with postgres_session_factory() as session:
        redemptions = tuple(await session.scalars(select(promotions_orm.PromotionRedemption)))
        transactions = tuple(await session.scalars(select(credits_orm.CreditTransaction)))
        user_credit = await session.get(
            credits_orm.UserCredit,
            {"user_id": granted_user_id, "feature_key": "ocr"},
        )
        event_types = tuple(await session.scalars(select(OutboxEvent.event_type)))

    assert len(redemptions) == 1
    assert len(transactions) == 1
    assert user_credit is not None
    assert (user_credit.total_granted_count, user_credit.remaining_count) == (5, 5)
    assert Counter(event_types) == Counter({"PromotionRedemptionGranted": 1, "CreditGranted": 1})


async def test_redeem_signup_promotion_rolls_back_every_write_when_outer_commit_fails(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: signup outer transaction의 commit이 실패한다.
    user_id = uuid4()
    async with postgres_session_factory() as session:
        promotion_id = await seed_active_signup_campaign(session, benefit_amount=5)
        use_case = build_redeem_signup_promotion_command_use_case(
            session,
            FailingCommitUnitOfWork(delegate=SqlAlchemyUnitOfWork(session)),
        )

        # When: promotion grant까지 완료한 뒤 outer commit이 실패한다.
        with pytest.raises(PromotionRedemptionConflictError):
            await use_case.execute(
                RedeemSignupPromotionCommand(user_id=user_id, beneficiary_key=_BENEFICIARY_KEY)
            )

    # Then: promotion counter, redemption, credits ledger, 양쪽 outbox 모두 rollback된다.
    async with postgres_session_factory() as session:
        promotion = await session.get(promotions_orm.Promotion, promotion_id)
        assert promotion is not None
        assert promotion.times_redeemed == 0
        assert await count_rows(session, promotions_orm.PromotionRedemption) == 0
        assert await count_rows(session, credits_orm.CreditTransaction) == 0
        assert await count_rows(session, OutboxEvent) == 0
