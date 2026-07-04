from collections.abc import Callable
from datetime import UTC, datetime

from app.core.application.unit_of_work import UnitOfWork
from app.modules.promotions.application.commands.create_promotion_redemption.command import (
    CreatePromotionRedemptionCommand,
)
from app.modules.promotions.application.commands.create_promotion_redemption.result import (
    CreatePromotionRedemptionResult,
)
from app.modules.promotions.application.ports.credit_grant import (
    PromotionCreditGrant,
    PromotionCreditGrantPort,
)
from app.modules.promotions.application.ports.promotion_repository import (
    PromotionRepository,
)
from app.modules.promotions.domain.exceptions import PromotionNotFoundError
from app.modules.promotions.domain.model import Promotion, PromotionRedemption


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CreatePromotionRedemptionCommandUseCase:
    def __init__(
        self,
        *,
        promotion_repository: PromotionRepository,
        credit_grant_port: PromotionCreditGrantPort,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._promotion_repository = promotion_repository
        self._credit_grant_port = credit_grant_port
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def execute(
        self,
        command: CreatePromotionRedemptionCommand,
    ) -> CreatePromotionRedemptionResult:
        idempotency_key = f"promotionRedemption:{command.promotion_id}:{command.user_id}"
        existing = await self._promotion_repository.find_redemption_by_idempotency_key(
            idempotency_key=idempotency_key
        )
        if existing is not None:
            promotion = await self._promotion_repository.find_promotion_for_update(
                promotion_id=existing.promotion_id,
            )
            if promotion is None:
                raise PromotionNotFoundError()
            balance = await self._credit_grant_port.get_ocr_credit_balance(
                user_id=command.user_id,
            )
            return _result(
                redemption=existing,
                promotion=promotion,
                already_redeemed=True,
                credit_granted=False,
                credit_balance_after=balance.total_granted_count,
                credit_remaining_after=balance.remaining_count,
            )

        promotion = await self._promotion_repository.find_promotion_for_update(
            promotion_id=command.promotion_id,
        )
        if promotion is None:
            raise PromotionNotFoundError()

        already_redeemed = await self._promotion_repository.find_redemption_by_user_and_promotion(
            user_id=command.user_id,
            promotion_id=command.promotion_id,
        )
        if already_redeemed is not None:
            balance = await self._credit_grant_port.get_ocr_credit_balance(
                user_id=command.user_id,
            )
            return _result(
                redemption=already_redeemed,
                promotion=promotion,
                already_redeemed=True,
                credit_granted=False,
                credit_balance_after=balance.total_granted_count,
                credit_remaining_after=balance.remaining_count,
            )

        return await self._redeem(
            command=command,
            promotion=promotion,
            idempotency_key=idempotency_key,
        )

    async def _redeem(
        self,
        *,
        command: CreatePromotionRedemptionCommand,
        promotion: Promotion,
        idempotency_key: str,
    ) -> CreatePromotionRedemptionResult:
        now = self._clock()
        promotion.ensure_redeemable(at=now)
        user_redemption_count = await self._promotion_repository.count_user_redemptions(
            user_id=command.user_id,
            promotion_id=promotion.id,
        )
        promotion.ensure_user_can_redeem(user_redemption_count=user_redemption_count)

        redemption = PromotionRedemption.create_granted(
            promotion_id=promotion.id,
            promotion_code_id=None,
            user_id=command.user_id,
            idempotency_key=idempotency_key,
            redeemed_at=now,
        )
        promotion.record_redemption()
        await self._promotion_repository.create_redemption(redemption=redemption)
        await self._promotion_repository.save_promotion(promotion=promotion)
        grant_result = await self._credit_grant_port.grant_ocr_credit(
            grant=_credit_grant(
                redemption=redemption,
                amount=promotion.benefit_amount.value,
                idempotency_key=idempotency_key,
            )
        )
        await self._unit_of_work.commit()
        return _result(
            redemption=redemption,
            promotion=promotion,
            already_redeemed=False,
            credit_granted=True,
            credit_balance_after=grant_result.credit_balance_after,
            credit_remaining_after=grant_result.credit_remaining_after,
        )


def _credit_grant(
    *,
    redemption: PromotionRedemption,
    amount: int,
    idempotency_key: str,
) -> PromotionCreditGrant:
    return PromotionCreditGrant(
        user_id=redemption.user_id,
        amount=amount,
        redemption_id=redemption.id,
        idempotency_key=idempotency_key,
    )


def _result(
    *,
    redemption: PromotionRedemption,
    promotion: Promotion,
    already_redeemed: bool,
    credit_granted: bool,
    credit_balance_after: int | None,
    credit_remaining_after: int | None,
) -> CreatePromotionRedemptionResult:
    return CreatePromotionRedemptionResult(
        redemption_id=redemption.id,
        promotion_id=redemption.promotion_id,
        promotion_code_id=redemption.promotion_code_id,
        status=redemption.status,
        already_redeemed=already_redeemed,
        credit_granted=credit_granted,
        benefit_amount=promotion.benefit_amount.value,
        remaining_redemptions=_remaining_redemptions(promotion),
        credit_balance_after=credit_balance_after,
        credit_remaining_after=credit_remaining_after,
    )


def _remaining_redemptions(promotion: Promotion) -> int | None:
    if promotion.max_redemptions is None:
        return None
    return max(promotion.max_redemptions - promotion.times_redeemed, 0)
