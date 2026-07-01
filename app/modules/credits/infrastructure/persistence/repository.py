from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credits.application.ports.credit_repository import (
    CreditRepository,
    CreditTransactionCursor,
    CreditTransactionListResult,
)
from app.modules.credits.domain import CreditBalance, FeatureKey
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
