from collections.abc import Callable
from datetime import UTC, datetime

from app.core.application.unit_of_work import UnitOfWork
from app.modules.promotions.application.commands.create_promotion_code_redemption.command import (
    CreatePromotionCodeRedemptionCommand,
)
from app.modules.promotions.application.commands.create_promotion_redemption.result import (
    CreatePromotionRedemptionResult,
)
from app.modules.promotions.application.commands.create_promotion_redemption.use_case import (
    _banner_image_url,
    _credit_grant,
    _result,
)
from app.modules.promotions.application.ports.credit_grant import PromotionCreditGrantPort
from app.modules.promotions.application.ports.promotion_repository import PromotionRepository
from app.modules.promotions.domain.exceptions import (
    PromotionCodeNotFoundError,
    PromotionNotFoundError,
)
from app.modules.promotions.domain.model import PromotionCode, PromotionRedemption


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CreatePromotionCodeRedemptionCommandUseCase:
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
        command: CreatePromotionCodeRedemptionCommand,
    ) -> CreatePromotionRedemptionResult:
        code = await self._promotion_repository.find_code_by_code_for_update(code=command.code)
        if code is None:
            raise PromotionCodeNotFoundError()

        idempotency_key = _idempotency_key(command, code)
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
            content = await self._promotion_repository.find_content_by_promotion_id(
                promotion_id=promotion.id,
            )
            return _result(
                redemption=existing,
                promotion=promotion,
                banner_image_url=_banner_image_url(content),
                already_redeemed=True,
                credit_granted=False,
                credit_balance_after=balance.total_granted_count,
                credit_remaining_after=balance.remaining_count,
            )

        promotion = await self._promotion_repository.find_promotion_for_update(
            promotion_id=code.promotion_id,
        )
        if promotion is None:
            raise PromotionNotFoundError()

        return await self._redeem(
            command=command,
            code=code,
            idempotency_key=idempotency_key,
        )

    async def _redeem(
        self,
        *,
        command: CreatePromotionCodeRedemptionCommand,
        code: PromotionCode,
        idempotency_key: str,
    ) -> CreatePromotionRedemptionResult:
        now = self._clock()
        code.ensure_redeemable(at=now)
        promotion = await self._promotion_repository.find_promotion_for_update(
            promotion_id=code.promotion_id,
        )
        if promotion is None:
            raise PromotionNotFoundError()
        promotion.ensure_redeemable(at=now)
        user_redemption_count = await self._promotion_repository.count_user_redemptions(
            user_id=command.user_id,
            promotion_id=promotion.id,
        )
        promotion.ensure_user_can_redeem(user_redemption_count=user_redemption_count)

        redemption = PromotionRedemption.create_granted(
            promotion_id=promotion.id,
            promotion_code_id=code.id,
            user_id=command.user_id,
            idempotency_key=idempotency_key,
            redeemed_at=now,
        )
        promotion.record_redemption()
        code.record_redemption()
        await self._promotion_repository.create_redemption(redemption=redemption)
        await self._promotion_repository.save_promotion(promotion=promotion)
        await self._promotion_repository.save_code(code=code)
        grant_result = await self._credit_grant_port.grant_ocr_credit(
            grant=_credit_grant(
                redemption=redemption,
                amount=promotion.benefit_amount.value,
                idempotency_key=idempotency_key,
            )
        )
        await self._unit_of_work.commit()
        content = await self._promotion_repository.find_content_by_promotion_id(
            promotion_id=promotion.id,
        )
        return _result(
            redemption=redemption,
            promotion=promotion,
            banner_image_url=_banner_image_url(content),
            already_redeemed=False,
            credit_granted=True,
            credit_balance_after=grant_result.credit_balance_after,
            credit_remaining_after=grant_result.credit_remaining_after,
        )


def _idempotency_key(command: CreatePromotionCodeRedemptionCommand, code: PromotionCode) -> str:
    if command.idempotency_key is None:
        return f"promotionCodeRedemption:{code.id}:{command.user_id}"
    return f"promotionCodeRedemption:{code.id}:{command.user_id}:{command.idempotency_key}"
