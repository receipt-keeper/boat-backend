from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credits.application.ports.credit_repository import (
    CreditRepository,
    CreditTransactionAppend,
    CreditTransactionCursor,
    CreditTransactionHandle,
    CreditTransactionListResult,
    CreditTransactionSourceKey,
    CreditTransactionWriteConflictError,
)
from app.modules.credits.domain import (
    CreditBalance,
    FeatureKey,
    UserCredit,
)
from app.modules.credits.infrastructure.persistence import mapper, orm

_IDEMPOTENT_CREDIT_TRANSACTION_CONSTRAINTS = frozenset(
    {
        "ix_credit_transactions_idempotency_key_unique",
        "ix_credit_transactions_source_unique",
        "pk_user_credits",
    }
)


class SqlAlchemyCreditRepository(CreditRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_balance(self, *, user_id: UUID) -> CreditBalance:
        record = await self._session.get(
            orm.UserCredit,
            {"user_id": user_id, "feature_key": FeatureKey.OCR.value},
        )
        return mapper.user_credit_to_balance(record, user_id=user_id)

    async def get_user_credit_for_update(self, *, user_id: UUID) -> UserCredit:
        record = await self._session.scalar(
            select(orm.UserCredit)
            .where(
                orm.UserCredit.user_id == user_id,
                orm.UserCredit.feature_key == FeatureKey.OCR.value,
            )
            .with_for_update()
        )
        return mapper.user_credit_to_domain(record, user_id=user_id)

    async def save(self, *, user_credit: UserCredit) -> None:
        record = await self._session.get(
            orm.UserCredit,
            {"user_id": user_credit.id, "feature_key": user_credit.feature_key.value},
        )
        if record is None:
            self._session.add(
                orm.UserCredit(
                    user_id=user_credit.id,
                    feature_key=user_credit.feature_key.value,
                    total_granted_count=user_credit.total_granted_count,
                    used_count=user_credit.used_count,
                    remaining_count=user_credit.remaining_count,
                )
            )
            return

        record.total_granted_count = user_credit.total_granted_count
        record.used_count = user_credit.used_count
        record.remaining_count = user_credit.remaining_count

    async def append_transaction(
        self,
        *,
        transaction: CreditTransactionAppend,
    ) -> None:
        self._session.add(
            orm.CreditTransaction(
                user_id=transaction.user_id,
                feature_key=FeatureKey.OCR.value,
                reason=transaction.reason.value,
                action=transaction.action.value,
                amount=transaction.amount.value,
                source_type=(
                    transaction.source_type.value if transaction.source_type is not None else None
                ),
                source_id=transaction.source_id,
                idempotency_key=transaction.idempotency_key,
            )
        )

    async def flush_pending_writes(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if _integrity_constraint_name(exc) in _IDEMPOTENT_CREDIT_TRANSACTION_CONSTRAINTS:
                raise CreditTransactionWriteConflictError from exc
            raise

    async def exists_transaction_with_idempotency_key(
        self,
        *,
        idempotency_key: str,
    ) -> bool:
        exists = await self._session.scalar(
            select(orm.CreditTransaction.id)
            .where(orm.CreditTransaction.idempotency_key == idempotency_key)
            .limit(1)
        )
        return exists is not None

    async def exists_transaction_with_source(
        self,
        *,
        source: CreditTransactionSourceKey,
    ) -> bool:
        exists = await self._session.scalar(
            select(orm.CreditTransaction.id)
            .where(
                orm.CreditTransaction.source_type == source.source_type.value,
                orm.CreditTransaction.source_id == source.source_id,
                orm.CreditTransaction.user_id == source.user_id,
                orm.CreditTransaction.feature_key == FeatureKey.OCR.value,
                orm.CreditTransaction.action == source.action.value,
            )
            .limit(1)
        )
        return exists is not None

    async def delete_by_user_id(self, *, user_id: UUID) -> None:
        await self._session.execute(
            delete(orm.CreditTransaction).where(orm.CreditTransaction.user_id == user_id)
        )
        await self._session.execute(delete(orm.UserCredit).where(orm.UserCredit.user_id == user_id))

    async def find_transaction_by_idempotency_keys(
        self,
        *,
        idempotency_keys: Sequence[str],
    ) -> CreditTransactionHandle | None:
        if not idempotency_keys:
            return None
        row = (
            await self._session.execute(
                select(orm.CreditTransaction.id, orm.CreditTransaction.idempotency_key)
                .where(orm.CreditTransaction.idempotency_key.in_(idempotency_keys))
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        transaction_id, idempotency_key = row
        return CreditTransactionHandle(
            transaction_id=transaction_id,
            idempotency_key=idempotency_key,
        )

    async def set_transaction_purge_after(
        self,
        *,
        transaction_id: UUID,
        purge_after: datetime | None,
    ) -> None:
        await self._session.execute(
            update(orm.CreditTransaction)
            .where(orm.CreditTransaction.id == transaction_id)
            .values(purge_after=purge_after)
        )

    async def delete_user_credit_state_except_transactions(
        self,
        *,
        user_id: UUID,
        preserved_transaction_ids: Sequence[UUID],
    ) -> None:
        delete_transactions = delete(orm.CreditTransaction).where(
            orm.CreditTransaction.user_id == user_id
        )
        if preserved_transaction_ids:
            delete_transactions = delete_transactions.where(
                orm.CreditTransaction.id.notin_(preserved_transaction_ids)
            )
        await self._session.execute(delete_transactions)
        await self._session.execute(delete(orm.UserCredit).where(orm.UserCredit.user_id == user_id))

    async def list_transactions(
        self,
        *,
        user_id: UUID,
        cursor: CreditTransactionCursor | None,
        limit: int,
    ) -> CreditTransactionListResult:
        total_count = (
            await self._session.scalar(
                select(func.count())
                .select_from(orm.CreditTransaction)
                .where(
                    orm.CreditTransaction.user_id == user_id,
                    orm.CreditTransaction.feature_key == FeatureKey.OCR.value,
                )
            )
            or 0
        )
        query = (
            select(orm.CreditTransaction)
            .where(
                orm.CreditTransaction.user_id == user_id,
                orm.CreditTransaction.feature_key == FeatureKey.OCR.value,
            )
            .order_by(
                orm.CreditTransaction.created_at.asc(),
                orm.CreditTransaction.id.asc(),
            )
            .limit(limit + 1)
        )
        if cursor is not None:
            query = query.where(
                or_(
                    orm.CreditTransaction.created_at > cursor.created_at,
                    and_(
                        orm.CreditTransaction.created_at == cursor.created_at,
                        orm.CreditTransaction.id > cursor.transaction_id,
                    ),
                )
            )
        records = tuple(await self._session.scalars(query))
        return CreditTransactionListResult(
            transactions=tuple(
                mapper.transaction_to_list_item(record) for record in records[:limit]
            ),
            has_next=len(records) > limit,
            total_count=total_count,
        )


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    for candidate in (exc.orig, getattr(exc.orig, "__cause__", None)):
        constraint_name = getattr(candidate, "constraint_name", None)
        if isinstance(constraint_name, str):
            return constraint_name
    return None
