from datetime import UTC, date, datetime
from uuid import UUID

import anyio
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config.settings import Settings
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.main import create_app
from app.modules.promotions.domain.model import (
    Promotion,
    PromotionBenefitFeatureKey,
    PromotionContext,
    PromotionKind,
)
from app.modules.promotions.infrastructure.persistence import orm
from app.modules.promotions.infrastructure.persistence.repository import (
    SqlAlchemyPromotionRepository,
)
from app.modules.promotions.jobs.ensure_monthly_recharge_promotion import (
    ensure_monthly_recharge_promotion,
)

JULY_2026 = date(2026, 7, 1)
JULY_START_UTC = datetime(2026, 6, 30, 15, 0, tzinfo=UTC)
AUGUST_START_UTC = datetime(2026, 7, 31, 15, 0, tzinfo=UTC)
MONTHLY_PROMOTION_NAME = "월간 OCR 크레딧 충전 2026-07"
EXISTING_PROMOTION_ID = UUID("00000000-0000-0000-0000-000000000701")


async def test_ensure_monthly_recharge_promotion_creates_july_2026_kst_row(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await ensure_monthly_recharge_promotion(
            promotion_repository=SqlAlchemyPromotionRepository(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
            target_month=JULY_2026,
        )

        promotion = await _monthly_recharge_promotion(session)

    assert promotion is not None
    assert promotion.starts_at == JULY_START_UTC
    assert promotion.expires_at == AUGUST_START_UTC
    assert promotion.benefit_amount == 5
    assert promotion.context == PromotionContext.RECHARGE.value
    assert promotion.kind == PromotionKind.MONTHLY_ALLOWANCE.value
    assert promotion.max_redemptions_per_user == 1
    assert promotion.active is True
    assert promotion.max_redemptions is None
    assert promotion.name == MONTHLY_PROMOTION_NAME


async def test_ensure_monthly_recharge_promotion_is_idempotent_for_same_month(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        job_repository = SqlAlchemyPromotionRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)

        first_result = await ensure_monthly_recharge_promotion(
            promotion_repository=job_repository,
            unit_of_work=unit_of_work,
            target_month=JULY_2026,
        )
        second_result = await ensure_monthly_recharge_promotion(
            promotion_repository=job_repository,
            unit_of_work=unit_of_work,
            target_month=JULY_2026,
        )

        row_count = await _monthly_recharge_promotion_count(session)

    assert row_count == 1
    assert first_result.created is True
    assert second_result.created is False
    assert first_result.promotion_id == second_result.promotion_id


async def test_ensure_monthly_recharge_promotion_concurrent_duplicate_insert_converges_to_one_row(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    barrier = _SelectMissBarrier()
    results: list[str] = []
    created_results: list[bool] = []

    async def run_job() -> None:
        async with postgres_session_factory() as session:
            result = await ensure_monthly_recharge_promotion(
                promotion_repository=_BarrierSqlAlchemyPromotionRepository(session, barrier),
                unit_of_work=SqlAlchemyUnitOfWork(session),
                target_month=JULY_2026,
            )
            results.append(result.promotion_id)
            created_results.append(result.created)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(run_job)
        task_group.start_soon(run_job)

    async with postgres_session_factory() as session:
        row_count = await _monthly_recharge_promotion_count(session)

    assert row_count == 1
    assert set(created_results) == {False, True}
    assert len(set(results)) == 1


async def test_ensure_monthly_recharge_promotion_does_not_reset_times_redeemed(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_existing_monthly_recharge_promotion(session)

        await ensure_monthly_recharge_promotion(
            promotion_repository=SqlAlchemyPromotionRepository(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
            target_month=JULY_2026,
        )

        promotion = await _monthly_recharge_promotion(session)

    assert promotion is not None
    assert promotion.id == EXISTING_PROMOTION_ID
    assert promotion.name == MONTHLY_PROMOTION_NAME
    assert promotion.active is True
    assert promotion.expires_at == AUGUST_START_UTC
    assert promotion.max_redemptions is None
    assert promotion.max_redemptions_per_user == 1
    assert promotion.benefit_amount == 5
    assert promotion.times_redeemed == 7


async def test_duplicate_monthly_recharge_promotion_business_key_is_rejected_at_db_level(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_existing_monthly_recharge_promotion(session)
        session.add(
            orm.Promotion(
                id=UUID("00000000-0000-0000-0000-000000000702"),
                name="중복 월간 충전",
                active=True,
                starts_at=JULY_START_UTC,
                expires_at=AUGUST_START_UTC,
                max_redemptions=None,
                times_redeemed=0,
                max_redemptions_per_user=1,
                benefit_feature_key=PromotionBenefitFeatureKey.OCR.value,
                context=PromotionContext.RECHARGE.value,
                kind=PromotionKind.MONTHLY_ALLOWANCE.value,
                benefit_amount=5,
            )
        )

        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()
        await session.rollback()

    assert "uq_promotions_benefit_context_kind_starts_at" in str(exc_info.value.orig)


def test_monthly_recharge_job_does_not_add_admin_or_public_api() -> None:
    test_app = create_app(Settings(outbox_poller_enabled=False))

    openapi_schema = test_app.openapi()
    promotion_paths = {
        path for path in openapi_schema["paths"] if path.startswith("/api/v1/promotions")
    }

    assert promotion_paths == {
        "/api/v1/promotions",
        "/api/v1/promotions/redemptions",
        "/api/v1/promotions/{promotion_id}/redemptions",
    }


async def _seed_existing_monthly_recharge_promotion(session: AsyncSession) -> None:
    session.add(
        orm.Promotion(
            id=EXISTING_PROMOTION_ID,
            name="오래된 월간 충전명",
            active=False,
            starts_at=JULY_START_UTC,
            expires_at=None,
            max_redemptions=99,
            times_redeemed=7,
            max_redemptions_per_user=3,
            benefit_feature_key=PromotionBenefitFeatureKey.OCR.value,
            context=PromotionContext.RECHARGE.value,
            kind=PromotionKind.MONTHLY_ALLOWANCE.value,
            benefit_amount=1,
        )
    )
    await session.commit()


async def _monthly_recharge_promotion(session: AsyncSession) -> orm.Promotion | None:
    return await session.scalar(
        select(orm.Promotion)
        .where(
            orm.Promotion.benefit_feature_key == PromotionBenefitFeatureKey.OCR.value,
            orm.Promotion.context == PromotionContext.RECHARGE.value,
            orm.Promotion.kind == PromotionKind.MONTHLY_ALLOWANCE.value,
            orm.Promotion.starts_at == JULY_START_UTC,
        )
        .limit(1)
    )


async def _monthly_recharge_promotion_count(session: AsyncSession) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(orm.Promotion)
            .where(
                orm.Promotion.benefit_feature_key == PromotionBenefitFeatureKey.OCR.value,
                orm.Promotion.context == PromotionContext.RECHARGE.value,
                orm.Promotion.kind == PromotionKind.MONTHLY_ALLOWANCE.value,
                orm.Promotion.starts_at == JULY_START_UTC,
            )
        )
        or 0
    )


class _SelectMissBarrier:
    def __init__(self) -> None:
        self._lock = anyio.Lock()
        self._both_missing = anyio.Event()
        self._miss_count = 0

    async def wait_until_both_jobs_missed(self) -> None:
        async with self._lock:
            self._miss_count += 1
            if self._miss_count == 2:
                self._both_missing.set()
        await self._both_missing.wait()


class _BarrierSqlAlchemyPromotionRepository(SqlAlchemyPromotionRepository):
    def __init__(self, session: AsyncSession, barrier: _SelectMissBarrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def find_promotion_by_benefit_context_start_for_update(
        self,
        *,
        benefit_feature_key: PromotionBenefitFeatureKey,
        context: PromotionContext,
        kind: PromotionKind | None,
        starts_at: datetime,
    ) -> Promotion | None:
        promotion = await super().find_promotion_by_benefit_context_start_for_update(
            benefit_feature_key=benefit_feature_key,
            context=context,
            kind=kind,
            starts_at=starts_at,
        )
        if promotion is None:
            await self._barrier.wait_until_both_jobs_missed()
        return promotion
