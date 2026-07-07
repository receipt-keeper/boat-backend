import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Final
from uuid import uuid4
from zoneinfo import ZoneInfo

import anyio
from sqlalchemy.exc import IntegrityError

from app.core.application.unit_of_work import UnitOfWork
from app.core.config.settings import get_settings
from app.core.db.session import build_engine, build_session_factory
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.promotions.application.ports.promotion_repository import (
    PromotionRepository,
)
from app.modules.promotions.domain.model import (
    Promotion,
    PromotionBenefitAmount,
    PromotionBenefitFeatureKey,
    PromotionContext,
)
from app.modules.promotions.infrastructure.persistence.repository import (
    SqlAlchemyPromotionRepository,
)

SEOUL_TZ: Final = ZoneInfo("Asia/Seoul")
MONTHLY_RECHARGE_AMOUNT: Final = 5
MONTHLY_RECHARGE_USER_LIMIT: Final = 1

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EnsureMonthlyRechargePromotionResult:
    promotion_id: str
    created: bool
    starts_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class MonthlyRechargePromotionSpec:
    name: str
    starts_at: datetime
    expires_at: datetime
    benefit_amount: int = MONTHLY_RECHARGE_AMOUNT


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def ensure_monthly_recharge_promotion(
    *,
    promotion_repository: PromotionRepository,
    unit_of_work: UnitOfWork,
    target_month: date | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> EnsureMonthlyRechargePromotionResult:
    spec = _monthly_recharge_promotion_spec(target_month=target_month, clock=clock)
    promotion = await promotion_repository.find_promotion_by_benefit_context_start_for_update(
        benefit_feature_key=PromotionBenefitFeatureKey.OCR,
        context=PromotionContext.RECHARGE,
        starts_at=spec.starts_at,
    )
    created = promotion is None
    if promotion is None:
        promotion, created = await _create_or_load_monthly_recharge_promotion(
            promotion_repository=promotion_repository,
            unit_of_work=unit_of_work,
            spec=spec,
        )
    else:
        _apply_monthly_recharge_spec(promotion=promotion, spec=spec)
        await promotion_repository.save_promotion(promotion=promotion)

    await unit_of_work.commit()
    return EnsureMonthlyRechargePromotionResult(
        promotion_id=str(promotion.id),
        created=created,
        starts_at=promotion.starts_at,
        expires_at=promotion.expires_at or spec.expires_at,
    )


async def run(target_month: date | None = None) -> EnsureMonthlyRechargePromotionResult:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    try:
        sessions = build_session_factory(engine)
        async with sessions() as session:
            result = await ensure_monthly_recharge_promotion(
                promotion_repository=SqlAlchemyPromotionRepository(session),
                unit_of_work=SqlAlchemyUnitOfWork(session),
                target_month=target_month,
            )
    finally:
        await engine.dispose()

    logger.info(
        "%s 월간 OCR 크레딧 충전 프로모션을 보장했습니다.",
        result.starts_at.isoformat(),
    )
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    anyio.run(run)


def _monthly_recharge_promotion_spec(
    *,
    target_month: date | None,
    clock: Callable[[], datetime],
) -> MonthlyRechargePromotionSpec:
    month = _target_month_or_current(target_month=target_month, clock=clock)
    starts_at = datetime(month.year, month.month, 1, tzinfo=SEOUL_TZ)
    next_month = _next_month(month)
    expires_at = datetime(next_month.year, next_month.month, 1, tzinfo=SEOUL_TZ)
    return MonthlyRechargePromotionSpec(
        name=f"월간 OCR 크레딧 충전 {month:%Y-%m}",
        starts_at=starts_at.astimezone(UTC),
        expires_at=expires_at.astimezone(UTC),
    )


def _target_month_or_current(
    *,
    target_month: date | None,
    clock: Callable[[], datetime],
) -> date:
    if target_month is not None:
        return target_month.replace(day=1)
    return clock().astimezone(SEOUL_TZ).date().replace(day=1)


def _next_month(month: date) -> date:
    if month.month == 12:
        return date(month.year + 1, 1, 1)
    return date(month.year, month.month + 1, 1)


def _new_monthly_recharge_promotion(spec: MonthlyRechargePromotionSpec) -> Promotion:
    return Promotion.restore(
        promotion_id=uuid4(),
        name=spec.name,
        active=True,
        starts_at=spec.starts_at,
        expires_at=spec.expires_at,
        max_redemptions=None,
        times_redeemed=0,
        max_redemptions_per_user=MONTHLY_RECHARGE_USER_LIMIT,
        benefit_feature_key=PromotionBenefitFeatureKey.OCR,
        context=PromotionContext.RECHARGE,
        benefit_amount=spec.benefit_amount,
    )


async def _create_or_load_monthly_recharge_promotion(
    *,
    promotion_repository: PromotionRepository,
    unit_of_work: UnitOfWork,
    spec: MonthlyRechargePromotionSpec,
) -> tuple[Promotion, bool]:
    promotion = _new_monthly_recharge_promotion(spec)
    try:
        await promotion_repository.create_promotion(promotion=promotion)
    except IntegrityError:
        await unit_of_work.rollback()
        existing = await promotion_repository.find_promotion_by_benefit_context_start_for_update(
            benefit_feature_key=PromotionBenefitFeatureKey.OCR,
            context=PromotionContext.RECHARGE,
            starts_at=spec.starts_at,
        )
        if existing is None:
            raise
        _apply_monthly_recharge_spec(promotion=existing, spec=spec)
        await promotion_repository.save_promotion(promotion=existing)
        return existing, False
    return promotion, True


def _apply_monthly_recharge_spec(
    *,
    promotion: Promotion,
    spec: MonthlyRechargePromotionSpec,
) -> None:
    promotion.name = spec.name
    promotion.active = True
    promotion.starts_at = spec.starts_at
    promotion.expires_at = spec.expires_at
    promotion.max_redemptions = None
    promotion.max_redemptions_per_user = MONTHLY_RECHARGE_USER_LIMIT
    promotion.benefit_feature_key = PromotionBenefitFeatureKey.OCR
    promotion.context = PromotionContext.RECHARGE
    promotion.benefit_amount = PromotionBenefitAmount(value=spec.benefit_amount)


if __name__ == "__main__":
    main()
