from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credits.application.ports.credit_repository import (
    CreditRepository,
    CreditTransactionCursor,
    CreditTransactionListResult,
)
from app.modules.credits.domain import (
    CreditAction,
    CreditAmount,
    CreditBalance,
    CreditReason,
    FeatureKey,
    UserCredit,
)
from app.modules.credits.infrastructure.persistence import mapper, orm


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
        user_id: UUID,
        reason: CreditReason,
        action: CreditAction,
        amount: CreditAmount,
    ) -> None:
        self._session.add(
            orm.CreditTransaction(
                user_id=user_id,
                feature_key=FeatureKey.OCR.value,
                reason=reason.value,
                action=action.value,
                amount=amount.value,
            )
        )

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
