from dataclasses import dataclass
from uuid import UUID

from app.modules.promotions.domain.model import PromotionRedemptionStatus


@dataclass(frozen=True, slots=True)
class CreatePromotionRedemptionResult:
    redemption_id: UUID
    promotion_id: UUID
    promotion_code_id: UUID | None
    status: PromotionRedemptionStatus
    already_redeemed: bool
    credit_granted: bool
    benefit_amount: int
    remaining_redemptions: int | None
    credit_balance_after: int | None
    credit_remaining_after: int | None
