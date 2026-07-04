from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CreatePromotionRedemptionCommand:
    user_id: UUID
    promotion_id: UUID
