from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.credits.domain import (
    CreditAction,
    CreditAmount,
    CreditBalance,
    CreditReason,
    CreditSourceType,
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
class CreditTransactionAppend:
    user_id: UUID
    reason: CreditReason
    action: CreditAction
    amount: CreditAmount
    source_type: CreditSourceType | None = None
    source_id: UUID | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if (self.source_type is None) != (self.source_id is None):
            raise ValidationError(
                [
                    ErrorDetail(
                        field="source",
                        message="크레딧 출처 유형과 출처 ID는 함께 저장해야 합니다.",
                    )
                ]
            )


@dataclass(frozen=True, slots=True)
class CreditTransactionSourceKey:
    user_id: UUID
    source_type: CreditSourceType
    source_id: UUID
    action: CreditAction


@dataclass(frozen=True, slots=True)
class CreditTransactionListResult:
    transactions: tuple[CreditTransactionListItem, ...]
    has_next: bool
    total_count: int


@dataclass(frozen=True, slots=True)
class CreditTransactionHandle:
    transaction_id: UUID
    idempotency_key: str


class CreditTransactionWriteConflictError(RuntimeError):
    pass


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
        transaction: CreditTransactionAppend,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def flush_pending_writes(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def exists_transaction_with_idempotency_key(
        self,
        *,
        idempotency_key: str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def exists_transaction_with_source(
        self,
        *,
        source: CreditTransactionSourceKey,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_user_id(self, *, user_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def find_transaction_by_idempotency_keys(
        self,
        *,
        idempotency_keys: Sequence[str],
    ) -> CreditTransactionHandle | None:
        raise NotImplementedError

    @abstractmethod
    async def set_transaction_purge_after(
        self,
        *,
        transaction_id: UUID,
        purge_after: datetime | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_user_credit_state_except_transactions(
        self,
        *,
        user_id: UUID,
        preserved_transaction_ids: Sequence[UUID],
    ) -> None:
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
