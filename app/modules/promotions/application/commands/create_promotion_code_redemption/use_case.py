from collections.abc import Callable
from datetime import UTC, datetime

from app.core.application.unit_of_work import UnitOfWork
from app.modules.promotions.application.commands.create_promotion_code_redemption.command import (
    CreatePromotionCodeRedemptionCommand,
)
from app.modules.promotions.application.commands.create_promotion_redemption.result import (
    CreatePromotionRedemptionResult,
)
from app.modules.promotions.application.commands.redemption_executor import (
    PromotionRedemptionAttempt,
    PromotionRedemptionExecutor,
    PromotionRedemptionReplay,
)
from app.modules.promotions.application.ports.credit_grant import PromotionCreditGrantPort
from app.modules.promotions.application.ports.promotion_repository import PromotionRepository
from app.modules.promotions.domain.exceptions import (
    PromotionCodeNotFoundError,
    PromotionNotFoundError,
)
from app.modules.promotions.domain.model import PromotionCode


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
        self._redemption_executor = PromotionRedemptionExecutor(
            promotion_repository=promotion_repository,
            credit_grant_port=credit_grant_port,
            unit_of_work=unit_of_work,
            clock=clock,
        )

    async def execute(
        self,
        command: CreatePromotionCodeRedemptionCommand,
    ) -> CreatePromotionRedemptionResult:
        code = await self._promotion_repository.find_code_by_code_for_update(code=command.code)
        if code is None:
            raise PromotionCodeNotFoundError()

        idempotency_key = _idempotency_key(command, code)
        replayed = await self._redemption_executor.replay_if_existing(
            PromotionRedemptionReplay(
                user_id=command.user_id,
                idempotency_key=idempotency_key,
            )
        )
        if replayed is not None:
            return replayed

        promotion = await self._promotion_repository.find_promotion_for_update(
            promotion_id=code.promotion_id,
        )
        if promotion is None:
            raise PromotionNotFoundError()

        return await self._redemption_executor.redeem(
            PromotionRedemptionAttempt(
                user_id=command.user_id,
                promotion=promotion,
                promotion_code=code,
                idempotency_key=idempotency_key,
            )
        )


def _idempotency_key(command: CreatePromotionCodeRedemptionCommand, code: PromotionCode) -> str:
    if command.idempotency_key is None:
        return f"promotionCodeRedemption:{code.id}:{command.user_id}"
    return f"promotionCodeRedemption:{code.id}:{command.user_id}:{command.idempotency_key}"
