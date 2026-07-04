from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GetCurrentOcrCreditPromotionQuery:
    user_id: UUID
