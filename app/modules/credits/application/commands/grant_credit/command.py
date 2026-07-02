from dataclasses import dataclass
from uuid import UUID

from app.modules.credits.domain import CreditAmount, CreditReason


@dataclass(frozen=True, slots=True)
class GrantCreditCommand:
    user_id: UUID
    amount: CreditAmount
    reason: CreditReason
