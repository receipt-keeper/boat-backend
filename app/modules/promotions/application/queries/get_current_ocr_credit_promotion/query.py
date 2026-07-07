from dataclasses import dataclass
from uuid import UUID

from app.modules.promotions.domain.model import PromotionContext


@dataclass(frozen=True, slots=True)
class GetCurrentOcrCreditPromotionQuery:
    user_id: UUID
    context: PromotionContext | None = None
