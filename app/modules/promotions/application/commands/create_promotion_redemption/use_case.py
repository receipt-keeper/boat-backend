from collections.abc import Callable
from datetime import UTC, datetime
from typing import assert_never

from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.promotions.application.commands.create_promotion_redemption.command import (
    CreatePromotionRedemptionCommand,
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
from app.modules.promotions.application.ports.promotion_repository import (
    PromotionRepository,
)
from app.modules.promotions.domain.exceptions import PromotionNotFoundError
from app.modules.promotions.domain.model import PromotionContext, PromotionKind


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CreatePromotionRedemptionCommandUseCase:
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
        self._redemption_executor = PromotionRedemptionExecutor(
            promotion_repository=promotion_repository,
            credit_grant_port=credit_grant_port,
            unit_of_work=unit_of_work,
            event_publisher=event_publisher,
            clock=clock,
        )

    async def execute(
        self,
        command: CreatePromotionRedemptionCommand,
    ) -> CreatePromotionRedemptionResult:
        promotion = await self._promotion_repository.find_promotion_for_update(
            promotion_id=command.promotion_id,
        )
        if promotion is None:
            raise PromotionNotFoundError()
        match promotion.context:
            case PromotionContext.SIGNUP:
                raise PromotionNotFoundError()
            case PromotionContext.RECHARGE | None:
                pass
            case unreachable:
                assert_never(unreachable)
        if promotion.kind == PromotionKind.REWARDED_AD and command.idempotency_key is None:
            raise ValidationError(
                [
                    ErrorDetail(
                        field="Idempotency-Key",
                        message="광고 보상 프로모션 수령에는 Idempotency-Key 헤더가 필요합니다.",
                    )
                ]
            )

        idempotency_key = _idempotency_key(command)

        replayed = await self._redemption_executor.replay_if_existing(
            PromotionRedemptionReplay(
                user_id=command.user_id,
                idempotency_key=idempotency_key,
            )
        )
        if replayed is not None:
            return replayed

        return await self._redemption_executor.redeem(
            PromotionRedemptionAttempt(
                user_id=command.user_id,
                promotion=promotion,
                promotion_code=None,
                idempotency_key=idempotency_key,
            )
        )


def _idempotency_key(command: CreatePromotionRedemptionCommand) -> str:
    if command.idempotency_key is None:
        return f"promotionRedemption:{command.promotion_id}:{command.user_id}"
    return f"promotionRedemption:{command.promotion_id}:{command.user_id}:{command.idempotency_key}"
