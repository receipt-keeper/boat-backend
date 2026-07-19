import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.domain.exceptions import NotFoundError, ValidationError
from app.modules.promotions.application.ports.credit_grant import (
    PromotionCreditBalance,
    PromotionCreditGrant,
    PromotionCreditGrantResult,
)
from app.modules.promotions.dependencies import build_promotions_event_registry
from app.modules.promotions.domain.exceptions import (
    PromotionNotFoundError,
    PromotionRedemptionConflictError,
)
from app.modules.promotions.domain.model import (
    PromotionContext,
    PromotionKind,
    PromotionRedemptionStatus,
)
from app.modules.promotions.infrastructure.persistence import orm
from app.modules.promotions.tests.helpers import (
    BANNER_IMAGE_URL,
    EXPIRED_PROMOTION_ID,
    NOW,
    PROMOTION_ID,
    PROMOTION_IDEMPOTENCY_KEY,
    USER_ID,
    FakePromotionCreditGrantPort,
    promotion_command,
    promotion_use_case,
    seed_promotion,
    seed_promotion_content,
)

AD_ATTEMPT_1 = "00000000-0000-0000-0000-000000000001"
AD_ATTEMPT_2 = "00000000-0000-0000-0000-000000000002"
AD_ATTEMPT_3 = "00000000-0000-0000-0000-000000000003"


async def test_create_promotion_redemption_grants_credit_and_persists_redemption(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session, context=PromotionContext.RECHARGE.value)
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
    assert result.banner_image_url is None
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


async def test_create_promotion_redemption_rejects_signup_context_before_redemption_or_credit(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 공개 수령 대상이 아닌 가입 축하 프로모션이 있다.
    async with postgres_session_factory() as session:
        await seed_promotion(session, context=PromotionContext.SIGNUP.value)
        grant_port = FakePromotionCreditGrantPort()

        # When: 공개 프로모션 ID로 수령을 요청한다.
        with pytest.raises(PromotionNotFoundError):
            await promotion_use_case(session, grant_port).execute(promotion_command())

    # Then: 404 도메인 경로를 타며 redemption과 credit 지급은 발생하지 않는다.
    async with postgres_session_factory() as session:
        redemption = await session.scalar(select(orm.PromotionRedemption))

    assert redemption is None
    assert grant_port.grants == []


async def test_create_promotion_redemption_idempotent_retry_uses_current_response_surface(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session)
        await seed_promotion_content(session)
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
    assert first.banner_image_url == BANNER_IMAGE_URL
    assert second.banner_image_url == BANNER_IMAGE_URL
    assert second.remaining_redemptions == 0
    assert second.credit_balance_after == first.credit_balance_after
    assert second.credit_remaining_after == first.credit_remaining_after
    assert len(grant_port.grants) == grant_call_count
    assert grant_port.grants[0].idempotency_key == PROMOTION_IDEMPOTENCY_KEY


async def test_create_promotion_redemption_publishes_promotion_redemption_granted_once(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session)
        grant_port = FakePromotionCreditGrantPort()
        event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_promotions_event_registry(),
        )

        await promotion_use_case(session, grant_port, event_publisher=event_publisher).execute(
            promotion_command()
        )

    async with postgres_session_factory() as session:
        saved_outbox_events = tuple(await session.scalars(select(OutboxEvent)))

    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "PromotionRedemptionGranted"
    assert saved_outbox_events[0].payload["promotion_id"] == str(PROMOTION_ID)
    assert saved_outbox_events[0].payload["user_id"] == str(USER_ID)


async def test_create_promotion_redemption_replay_does_not_publish_new_outbox_row(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session)
        grant_port = FakePromotionCreditGrantPort()
        event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_promotions_event_registry(),
        )
        use_case = promotion_use_case(session, grant_port, event_publisher=event_publisher)

        # Given: 최초 redeem이 outbox row 1건을 남긴다.
        await use_case.execute(promotion_command())

    # 두 번째 호출은 별도 세션에서 수행한다 - replay_if_existing 분기가 신규
    # 상태 변경·이벤트 기록 없이 기존 redemption을 그대로 반환하는지 확인한다.
    async with postgres_session_factory() as session:
        grant_port = FakePromotionCreditGrantPort()
        event_publisher = OutboxEventPublisher(
            session=session,
            registry=build_promotions_event_registry(),
        )
        use_case = promotion_use_case(session, grant_port, event_publisher=event_publisher)

        second = await use_case.execute(promotion_command())

    async with postgres_session_factory() as session:
        saved_outbox_events = tuple(await session.scalars(select(OutboxEvent)))

    assert second.already_redeemed is True
    assert second.credit_granted is False
    # 멱등 replay 분기(신규 상태 변경 없음)에서 outbox 신규 row가 발생하지 않는다.
    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "PromotionRedemptionGranted"


async def test_create_promotion_redemption_returns_banner_image_url(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session)
        await seed_promotion_content(session)
        grant_port = FakePromotionCreditGrantPort()

        result = await promotion_use_case(session, grant_port).execute(promotion_command())

    assert result.status == PromotionRedemptionStatus.GRANTED
    assert result.banner_image_url == BANNER_IMAGE_URL


async def test_create_promotion_redemption_allows_distinct_attempts_within_user_limit(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await seed_promotion(session, max_redemptions_per_user=2)
        grant_port = FakePromotionCreditGrantPort()
        use_case = promotion_use_case(session, grant_port)

        first = await use_case.execute(promotion_command(idempotency_key="attempt-1"))
        second = await use_case.execute(promotion_command(idempotency_key="attempt-2"))

    assert first.already_redeemed is False
    assert second.already_redeemed is False
    assert first.credit_granted is True
    assert second.credit_granted is True
    assert len(grant_port.grants) == 2
    assert [grant.idempotency_key for grant in grant_port.grants] == [
        f"promotionRedemption:{PROMOTION_ID}:{USER_ID}:attempt-1",
        f"promotionRedemption:{PROMOTION_ID}:{USER_ID}:attempt-2",
    ]


async def test_rewarded_ad_redemption_requires_idempotency_key(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_rewarded_ad_promotion(session)
        grant_port = _rewarded_ad_grant_port(remaining_count=0)

        with pytest.raises(ValidationError) as exc_info:
            await promotion_use_case(session, grant_port).execute(promotion_command())

    assert exc_info.value.details[0].field == "Idempotency-Key"
    assert grant_port.grants == []


async def test_rewarded_ad_redemption_rejects_non_uuid_idempotency_key(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_rewarded_ad_promotion(session)
        grant_port = _rewarded_ad_grant_port(remaining_count=0)

        with pytest.raises(ValidationError) as exc_info:
            await promotion_use_case(session, grant_port).execute(
                promotion_command(idempotency_key="not-a-uuid")
            )

    assert "UUID 형식" in exc_info.value.details[0].message
    assert grant_port.grants == []


async def test_rewarded_ad_redemption_rejects_when_ocr_credit_remains(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_rewarded_ad_promotion(session)
        grant_port = _rewarded_ad_grant_port(remaining_count=1)

        with pytest.raises(PromotionRedemptionConflictError, match="남은 OCR 분석 횟수"):
            await promotion_use_case(session, grant_port).execute(
                promotion_command(idempotency_key=AD_ATTEMPT_1)
            )

    assert grant_port.grants == []


async def test_rewarded_ad_redemption_requires_consumption_between_daily_grants(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_rewarded_ad_promotion(session)
        grant_port = _rewarded_ad_grant_port(remaining_count=0)
        use_case = promotion_use_case(session, grant_port)

        first = await use_case.execute(promotion_command(idempotency_key=AD_ATTEMPT_1))
        replay = await use_case.execute(promotion_command(idempotency_key=AD_ATTEMPT_1))

        with pytest.raises(PromotionRedemptionConflictError, match="남은 OCR 분석 횟수"):
            await use_case.execute(promotion_command(idempotency_key=AD_ATTEMPT_2))

        grant_port.balance = PromotionCreditBalance(total_granted_count=2, remaining_count=0)
        second = await use_case.execute(promotion_command(idempotency_key=AD_ATTEMPT_2))
        grant_port.balance = PromotionCreditBalance(total_granted_count=4, remaining_count=0)

        with pytest.raises(PromotionRedemptionConflictError, match="이미 사용한 프로모션"):
            await use_case.execute(promotion_command(idempotency_key=AD_ATTEMPT_3))

    assert first.kind == PromotionKind.REWARDED_AD
    assert first.max_redemptions_per_user == 2
    assert first.remaining_redemptions_for_user == 1
    assert grant_port.grants[0].required_remaining_count == 0
    assert replay.redemption_id == first.redemption_id
    assert replay.already_redeemed is True
    assert second.remaining_redemptions_for_user == 0
    assert len(grant_port.grants) == 2


async def test_rewarded_ad_daily_limit_resets_at_kst_midnight(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_rewarded_ad_promotion(session)
        grant_port = _rewarded_ad_grant_port(remaining_count=0)
        current_use_case = promotion_use_case(session, grant_port)

        await current_use_case.execute(promotion_command(idempotency_key=AD_ATTEMPT_1))
        grant_port.balance = PromotionCreditBalance(total_granted_count=2, remaining_count=0)
        await current_use_case.execute(promotion_command(idempotency_key=AD_ATTEMPT_2))
        grant_port.balance = PromotionCreditBalance(total_granted_count=4, remaining_count=0)

        next_day = await promotion_use_case(
            session,
            grant_port,
            clock=lambda: NOW + timedelta(hours=3),
        ).execute(promotion_command(idempotency_key=AD_ATTEMPT_3))

    assert next_day.remaining_redemptions_for_user == 1
    assert len(grant_port.grants) == 3


async def test_rewarded_ad_concurrent_distinct_requests_grant_only_once(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_rewarded_ad_promotion(session)

    grant_port = _rewarded_ad_grant_port(remaining_count=0)
    async with (
        postgres_session_factory() as first_session,
        postgres_session_factory() as second_session,
    ):
        results = await asyncio.gather(
            promotion_use_case(first_session, grant_port).execute(
                promotion_command(idempotency_key=AD_ATTEMPT_1)
            ),
            promotion_use_case(second_session, grant_port).execute(
                promotion_command(idempotency_key=AD_ATTEMPT_2)
            ),
            return_exceptions=True,
        )

    successful = [result for result in results if not isinstance(result, BaseException)]
    conflicts = [
        result for result in results if isinstance(result, PromotionRedemptionConflictError)
    ]
    assert len(successful) == 1
    assert len(conflicts) == 1
    assert len(grant_port.grants) == 1


async def _seed_rewarded_ad_promotion(session: AsyncSession) -> None:
    await seed_promotion(
        session,
        context=PromotionContext.RECHARGE.value,
        kind=PromotionKind.REWARDED_AD.value,
        max_redemptions=None,
        max_redemptions_per_user=2,
        expires_at=None,
        benefit_amount=2,
    )


def _rewarded_ad_grant_port(*, remaining_count: int) -> FakePromotionCreditGrantPort:
    return FakePromotionCreditGrantPort(
        result=PromotionCreditGrantResult(
            credit_balance_after=2,
            credit_remaining_after=2,
        ),
        balance=PromotionCreditBalance(
            total_granted_count=0,
            remaining_count=remaining_count,
        ),
    )


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
