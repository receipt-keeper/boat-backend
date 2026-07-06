from dataclasses import dataclass
from uuid import UUID

from app.core.domain.events import DomainEvent
from app.modules.credits.domain.value_objects import CreditReason, CreditSourceType


@dataclass(frozen=True, kw_only=True)
class CreditGranted(DomainEvent):
    user_id: UUID
    amount: int
    reason: CreditReason
    source_type: CreditSourceType | None
    source_id: UUID | None
    idempotency_key: str | None


@dataclass(frozen=True, kw_only=True)
class CreditUsed(DomainEvent):
    user_id: UUID
    amount: int
    reason: CreditReason


@dataclass(frozen=True, kw_only=True)
class UserCreditsDeleted(DomainEvent):
    user_id: UUID
