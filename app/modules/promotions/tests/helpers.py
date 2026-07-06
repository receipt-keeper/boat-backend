from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.event_publisher import EventPublisher
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.promotions.application.commands.create_promotion_code_redemption.command import (
    CreatePromotionCodeRedemptionCommand,
)
from app.modules.promotions.application.commands.create_promotion_code_redemption.use_case import (
    CreatePromotionCodeRedemptionCommandUseCase,
)
from app.modules.promotions.application.commands.create_promotion_redemption.command import (
    CreatePromotionRedemptionCommand,
)
from app.modules.promotions.application.commands.create_promotion_redemption.use_case import (
    CreatePromotionRedemptionCommandUseCase,
)
from app.modules.promotions.application.ports.credit_grant import (
    PromotionCreditBalance,
    PromotionCreditGrant,
    PromotionCreditGrantPort,
    PromotionCreditGrantResult,
)
from app.modules.promotions.dependencies import build_promotions_event_registry
from app.modules.promotions.infrastructure.persistence import orm
from app.modules.promotions.infrastructure.persistence.repository import (
    SqlAlchemyPromotionRepository,
)

NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000101")
PROMOTION_ID = UUID("00000000-0000-0000-0000-000000000201")
EXPIRED_PROMOTION_ID = UUID("00000000-0000-0000-0000-000000000202")
CODE_ID = UUID("00000000-0000-0000-0000-000000000301")
PROMOTION_CONTENT_ID = UUID("00000000-0000-0000-0000-000000000401")
BANNER_IMAGE_URL = "/files/00000000-0000-0000-0000-000000000901/content"
PROMOTION_IDEMPOTENCY_KEY = f"promotionRedemption:{PROMOTION_ID}:{USER_ID}"
CODE_IDEMPOTENCY_KEY = f"promotionCodeRedemption:{CODE_ID}:{USER_ID}"


@dataclass(slots=True)  # noqa: RUF100  # noqa: MUTABLE_OK
class FakePromotionCreditGrantPort(PromotionCreditGrantPort):
    grants: list[PromotionCreditGrant] = field(default_factory=list)
    result: PromotionCreditGrantResult = field(
        default_factory=lambda: PromotionCreditGrantResult(
            credit_balance_after=3,
            credit_remaining_after=3,
        )
    )

    async def grant_ocr_credit(
        self,
        *,
        grant: PromotionCreditGrant,
    ) -> PromotionCreditGrantResult:
        self.grants.append(grant)
        return self.result

    async def get_ocr_credit_balance(
        self,
        *,
        user_id: UUID,
    ) -> PromotionCreditBalance:
        return PromotionCreditBalance(
            total_granted_count=self.result.credit_balance_after or 0,
            remaining_count=self.result.credit_remaining_after or 0,
        )


def _event_publisher_for(
    session: AsyncSession,
    event_publisher: EventPublisher | None,
) -> EventPublisher:
    if event_publisher is not None:
        return event_publisher
    return OutboxEventPublisher(session=session, registry=build_promotions_event_registry())


def promotion_use_case(
    session: AsyncSession,
    grant_port: FakePromotionCreditGrantPort,
    *,
    event_publisher: EventPublisher | None = None,
) -> CreatePromotionRedemptionCommandUseCase:
    return CreatePromotionRedemptionCommandUseCase(
        promotion_repository=SqlAlchemyPromotionRepository(session),
        credit_grant_port=grant_port,
        unit_of_work=SqlAlchemyUnitOfWork(session),
        event_publisher=_event_publisher_for(session, event_publisher),
        clock=lambda: NOW,
    )


def code_use_case(
    session: AsyncSession,
    grant_port: FakePromotionCreditGrantPort,
    *,
    event_publisher: EventPublisher | None = None,
) -> CreatePromotionCodeRedemptionCommandUseCase:
    return CreatePromotionCodeRedemptionCommandUseCase(
        promotion_repository=SqlAlchemyPromotionRepository(session),
        credit_grant_port=grant_port,
        unit_of_work=SqlAlchemyUnitOfWork(session),
        event_publisher=_event_publisher_for(session, event_publisher),
        clock=lambda: NOW,
    )


def promotion_command(
    *,
    promotion_id: UUID = PROMOTION_ID,
    idempotency_key: str | None = None,
) -> CreatePromotionRedemptionCommand:
    return CreatePromotionRedemptionCommand(
        user_id=USER_ID,
        promotion_id=promotion_id,
        idempotency_key=idempotency_key,
    )


def code_command(
    *,
    code: str = "WELCOME2026",
    idempotency_key: str | None = None,
) -> CreatePromotionCodeRedemptionCommand:
    return CreatePromotionCodeRedemptionCommand(
        user_id=USER_ID,
        code=code,
        idempotency_key=idempotency_key,
    )


async def seed_promotion(
    session: AsyncSession,
    *,
    promotion_id: UUID = PROMOTION_ID,
    active: bool = True,
    starts_at: datetime = NOW - timedelta(days=1),
    expires_at: datetime | None = NOW + timedelta(days=1),
    max_redemptions: int | None = 10,
    times_redeemed: int = 0,
    max_redemptions_per_user: int = 1,
) -> None:
    session.add(
        orm.Promotion(
            id=promotion_id,
            name="OCR credit promotion",
            active=active,
            starts_at=starts_at,
            expires_at=expires_at,
            max_redemptions=max_redemptions,
            times_redeemed=times_redeemed,
            max_redemptions_per_user=max_redemptions_per_user,
            benefit_feature_key="ocr",
            benefit_amount=3,
        )
    )
    await session.commit()


async def seed_promotion_content(
    session: AsyncSession,
    *,
    promotion_id: UUID = PROMOTION_ID,
    banner_image_url: str | None = BANNER_IMAGE_URL,
) -> None:
    session.add(
        orm.PromotionContent(
            id=PROMOTION_CONTENT_ID,
            promotion_id=promotion_id,
            banner_image_url=banner_image_url,
        )
    )
    await session.commit()


async def seed_code(
    session: AsyncSession,
    *,
    active: bool = True,
    starts_at: datetime | None = NOW - timedelta(days=1),
    expires_at: datetime | None = NOW + timedelta(days=1),
    max_redemptions: int | None = 10,
    times_redeemed: int = 0,
) -> None:
    session.add(
        orm.PromotionCode(
            id=CODE_ID,
            promotion_id=PROMOTION_ID,
            code="WELCOME2026",
            active=active,
            starts_at=starts_at,
            expires_at=expires_at,
            max_redemptions=max_redemptions,
            times_redeemed=times_redeemed,
        )
    )
    await session.commit()
