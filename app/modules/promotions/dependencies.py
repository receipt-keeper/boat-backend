from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.outbox.serialization import EventTypeRegistry
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.application.commands.grant_credit.use_case import GrantCreditCommandUseCase
from app.modules.credits.application.queries.get_credit_balance.query import (
    GetCreditBalanceQuery,
)
from app.modules.credits.application.queries.get_credit_balance.use_case import (
    GetCreditBalanceQueryUseCase,
)
from app.modules.credits.dependencies import (
    build_credit_balance_query_use_case,
    build_deferred_grant_credit_command_use_case,
    get_credit_balance_query_use_case,
    get_deferred_grant_credit_command_use_case,
)
from app.modules.credits.domain import CreditAmount, CreditReason, CreditSourceType
from app.modules.credits.domain.exceptions import CreditBalancePreconditionError
from app.modules.promotions.application.commands.create_promotion_code_redemption.use_case import (
    CreatePromotionCodeRedemptionCommandUseCase,
)
from app.modules.promotions.application.commands.create_promotion_redemption.use_case import (
    CreatePromotionRedemptionCommandUseCase,
)
from app.modules.promotions.application.commands.redeem_signup_promotion.use_case import (
    RedeemSignupPromotionCommandUseCase,
)
from app.modules.promotions.application.ports.credit_grant import (
    PromotionCreditBalance,
    PromotionCreditGrant,
    PromotionCreditGrantPort,
    PromotionCreditGrantRejectedError,
    PromotionCreditGrantResult,
)
from app.modules.promotions.application.ports.promotion_repository import PromotionRepository
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.use_case import (
    GetCurrentOcrCreditPromotionQueryUseCase,
)
from app.modules.promotions.domain.events import PromotionRedemptionGranted
from app.modules.promotions.infrastructure.persistence.repository import (
    SqlAlchemyPromotionRepository,
)


def build_promotions_event_registry() -> EventTypeRegistry:
    registry = EventTypeRegistry()
    registry.register(PromotionRedemptionGranted)
    return registry


def _build_outbox_event_publisher(session: AsyncSession) -> EventPublisher:
    return OutboxEventPublisher(session=session, registry=build_promotions_event_registry())


def build_redeem_signup_promotion_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> RedeemSignupPromotionCommandUseCase:
    credit_grant_port = CreditsPromotionCreditGrantPort(
        grant_credit_command_use_case=build_deferred_grant_credit_command_use_case(session),
        credit_balance_query_use_case=build_credit_balance_query_use_case(session),
    )
    return RedeemSignupPromotionCommandUseCase(
        promotion_repository=SqlAlchemyPromotionRepository(session),
        credit_grant_port=credit_grant_port,
        unit_of_work=unit_of_work,
        event_publisher=_build_outbox_event_publisher(session),
    )


class CreditsPromotionCreditGrantPort(PromotionCreditGrantPort):
    def __init__(
        self,
        *,
        grant_credit_command_use_case: GrantCreditCommandUseCase,
        credit_balance_query_use_case: GetCreditBalanceQueryUseCase,
    ) -> None:
        self._grant_credit_command_use_case = grant_credit_command_use_case
        self._credit_balance_query_use_case = credit_balance_query_use_case

    async def grant_ocr_credit(
        self,
        *,
        grant: PromotionCreditGrant,
    ) -> PromotionCreditGrantResult:
        try:
            grant_result = await self._grant_credit_command_use_case.execute(
                GrantCreditCommand(
                    user_id=grant.user_id,
                    amount=CreditAmount(value=grant.amount),
                    reason=CreditReason.EVENT_OCR_ALLOWANCE,
                    source_type=CreditSourceType.PROMOTION_REDEMPTION,
                    source_id=grant.redemption_id,
                    idempotency_key=grant.idempotency_key,
                    required_remaining_count=grant.required_remaining_count,
                )
            )
        except CreditBalancePreconditionError as exc:
            raise PromotionCreditGrantRejectedError from exc
        return PromotionCreditGrantResult(
            credit_balance_after=grant_result.total_granted_count,
            credit_remaining_after=grant_result.remaining_count,
        )

    async def get_ocr_credit_balance(
        self,
        *,
        user_id: UUID,
    ) -> PromotionCreditBalance:
        balance = await self._credit_balance_query_use_case.execute(
            GetCreditBalanceQuery(user_id=user_id)
        )
        return PromotionCreditBalance(
            total_granted_count=balance.total_granted_count,
            remaining_count=balance.remaining_count,
        )


async def get_promotion_repository(session: AsyncSessionDep) -> PromotionRepository:
    return SqlAlchemyPromotionRepository(session)


async def get_promotion_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


async def get_promotion_credit_grant_port(
    grant_credit_command_use_case: Annotated[
        GrantCreditCommandUseCase,
        Depends(get_deferred_grant_credit_command_use_case),
    ],
    credit_balance_query_use_case: Annotated[
        GetCreditBalanceQueryUseCase,
        Depends(get_credit_balance_query_use_case),
    ],
) -> PromotionCreditGrantPort:
    return CreditsPromotionCreditGrantPort(
        grant_credit_command_use_case=grant_credit_command_use_case,
        credit_balance_query_use_case=credit_balance_query_use_case,
    )


async def get_current_ocr_credit_promotion_query_use_case(
    promotion_repository: Annotated[PromotionRepository, Depends(get_promotion_repository)],
) -> GetCurrentOcrCreditPromotionQueryUseCase:
    return GetCurrentOcrCreditPromotionQueryUseCase(promotion_repository=promotion_repository)


async def get_promotion_event_publisher(session: AsyncSessionDep) -> EventPublisher:
    return _build_outbox_event_publisher(session)


async def get_create_promotion_redemption_command_use_case(
    promotion_repository: Annotated[PromotionRepository, Depends(get_promotion_repository)],
    credit_grant_port: Annotated[
        PromotionCreditGrantPort,
        Depends(get_promotion_credit_grant_port),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_promotion_unit_of_work)],
    event_publisher: Annotated[EventPublisher, Depends(get_promotion_event_publisher)],
) -> CreatePromotionRedemptionCommandUseCase:
    return CreatePromotionRedemptionCommandUseCase(
        promotion_repository=promotion_repository,
        credit_grant_port=credit_grant_port,
        unit_of_work=unit_of_work,
        event_publisher=event_publisher,
    )


async def get_create_promotion_code_redemption_command_use_case(
    promotion_repository: Annotated[PromotionRepository, Depends(get_promotion_repository)],
    credit_grant_port: Annotated[
        PromotionCreditGrantPort,
        Depends(get_promotion_credit_grant_port),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_promotion_unit_of_work)],
    event_publisher: Annotated[EventPublisher, Depends(get_promotion_event_publisher)],
) -> CreatePromotionCodeRedemptionCommandUseCase:
    return CreatePromotionCodeRedemptionCommandUseCase(
        promotion_repository=promotion_repository,
        credit_grant_port=credit_grant_port,
        unit_of_work=unit_of_work,
        event_publisher=event_publisher,
    )


CurrentOcrCreditPromotionQueryUseCaseDep = Annotated[
    GetCurrentOcrCreditPromotionQueryUseCase,
    Depends(get_current_ocr_credit_promotion_query_use_case),
]
CreatePromotionRedemptionCommandUseCaseDep = Annotated[
    CreatePromotionRedemptionCommandUseCase,
    Depends(get_create_promotion_redemption_command_use_case),
]
CreatePromotionCodeRedemptionCommandUseCaseDep = Annotated[
    CreatePromotionCodeRedemptionCommandUseCase,
    Depends(get_create_promotion_code_redemption_command_use_case),
]
