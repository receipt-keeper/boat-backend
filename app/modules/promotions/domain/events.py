from dataclasses import dataclass
from uuid import UUID

from app.core.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class PromotionRedemptionGranted(DomainEvent):
    redemption_id: UUID
    promotion_id: UUID
    user_id: UUID
    promotion_code_id: UUID | None
    benefit_amount: int
    idempotency_key: str
