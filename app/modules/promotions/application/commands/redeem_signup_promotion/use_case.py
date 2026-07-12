from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.modules.promotions.application.commands.redeem_signup_promotion.command import (
    RedeemSignupPromotionCommand,
)
from app.modules.promotions.application.commands.redeem_signup_promotion.result import (
    RedeemSignupPromotionResult,
)
from app.modules.promotions.application.ports.credit_grant import (
    PromotionCreditGrant,
    PromotionCreditGrantPort,
)
from app.modules.promotions.application.ports.promotion_repository import PromotionRepository
from app.modules.promotions.domain.model import PromotionContext, PromotionRedemption


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RedeemSignupPromotionCommandUseCase:
    def __init__(
        self,
        *,
        promotion_repository: PromotionRepository,
        credit_grant_port: PromotionCreditGrantPort,
        unit_of_work: UnitOfWork,
        event_publisher: EventPublisher,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._promotion_repository = promotion_repository
        self._credit_grant_port = credit_grant_port
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher
        self._clock = clock

    async def execute(
        self,
        command: RedeemSignupPromotionCommand,
    ) -> RedeemSignupPromotionResult:
        now = self._clock()
        promotion = await self._promotion_repository.find_current_ocr_credit_promotion_for_update(
            at=now,
            context=PromotionContext.SIGNUP,
        )
        if promotion is None:
            return RedeemSignupPromotionResult(granted=False)

        existing = await self._promotion_repository.find_redemption_by_promotion_and_beneficiary(
            promotion_id=promotion.id,
            beneficiary_key=command.beneficiary_key,
        )
        if existing is not None:
            return RedeemSignupPromotionResult(granted=False)

        promotion.ensure_redeemable(at=now)
        redemption_id = uuid4()
        redemption = PromotionRedemption.create_granted(
            promotion_id=promotion.id,
            promotion_code_id=None,
            user_id=command.user_id,
            beneficiary_key=command.beneficiary_key,
            idempotency_key=_redemption_idempotency_key(
                promotion_id=promotion.id,
                redemption_id=redemption_id,
            ),
            redeemed_at=now,
            benefit_amount=promotion.benefit_amount.value,
            redemption_id=redemption_id,
        )
        promotion.record_redemption()
        await self._promotion_repository.create_redemption(redemption=redemption)
        await self._promotion_repository.save_promotion(promotion=promotion)
        await self._event_publisher.publish(redemption.pull_events())
        await self._credit_grant_port.grant_ocr_credit(
            grant=PromotionCreditGrant(
                user_id=command.user_id,
                amount=promotion.benefit_amount.value,
                redemption_id=redemption.id,
                idempotency_key=_credit_idempotency_key(
                    promotion_id=promotion.id,
                    redemption_id=redemption.id,
                ),
            )
        )
        await self._unit_of_work.commit()
        return RedeemSignupPromotionResult(granted=True)


def _redemption_idempotency_key(*, promotion_id: UUID, redemption_id: UUID) -> str:
    return f"signupPromotionRedemption:{promotion_id}:{redemption_id}"


def _credit_idempotency_key(*, promotion_id: UUID, redemption_id: UUID) -> str:
    return f"signupPromotionCredit:{promotion_id}:{redemption_id}"
