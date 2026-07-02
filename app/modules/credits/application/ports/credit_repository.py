from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.credits.domain import (
    CreditAction,
    CreditAmount,
    CreditBalance,
    CreditReason,
    UserCredit,
)


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
    amount: CreditAmount
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
    async def get_user_credit_for_update(self, *, user_id: UUID) -> UserCredit:
        raise NotImplementedError

    @abstractmethod
    async def save(self, *, user_credit: UserCredit) -> None:
        raise NotImplementedError

    @abstractmethod
    async def append_transaction(
        self,
        *,
        user_id: UUID,
        reason: CreditReason,
        action: CreditAction,
        amount: CreditAmount,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_user_id(self, *, user_id: UUID) -> None:
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
