from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PromotionCreditGrant:
    user_id: UUID
    amount: int
    redemption_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class PromotionCreditGrantResult:
    credit_balance_after: int | None
    credit_remaining_after: int | None


@dataclass(frozen=True, slots=True)
class PromotionCreditBalance:
    total_granted_count: int
    remaining_count: int


class PromotionCreditGrantPort(Protocol):
    async def grant_ocr_credit(
        self,
        *,
        grant: PromotionCreditGrant,
    ) -> PromotionCreditGrantResult: ...

    async def get_ocr_credit_balance(
        self,
        *,
        user_id: UUID,
    ) -> PromotionCreditBalance: ...
