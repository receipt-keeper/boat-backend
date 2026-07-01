from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.credits.domain import CreditAction, CreditBalance, CreditReason


@dataclass(frozen=True, slots=True)
class CreditTransactionCursor:
    created_at: datetime
    transaction_id: UUID


@dataclass(frozen=True, slots=True)
class CreditTransactionListItem:
    transaction_id: UUID
    user_id: UUID
    reason: CreditReason
    action: CreditAction
    amount: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CreditTransactionListResult:
    transactions: tuple[CreditTransactionListItem, ...]
    has_next: bool
    total_count: int


class CreditRepository(ABC):
    @abstractmethod
    async def get_balance(self, *, user_id: UUID) -> CreditBalance:
        raise NotImplementedError

    @abstractmethod
    async def list_transactions(
        self,
        *,
        user_id: UUID,
        cursor: CreditTransactionCursor | None,
        limit: int,
    ) -> CreditTransactionListResult:
        raise NotImplementedError
