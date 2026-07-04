from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.promotions.domain.model import PromotionRedemptionStatus


@dataclass(frozen=True, slots=True)
class GetCurrentOcrCreditPromotionResult:
    promotion_id: UUID
    name: str
    benefit_amount: int
    remaining_redemptions: int | None
    starts_at: datetime
    expires_at: datetime | None
    already_redeemed: bool
    redemption_status: PromotionRedemptionStatus | None
