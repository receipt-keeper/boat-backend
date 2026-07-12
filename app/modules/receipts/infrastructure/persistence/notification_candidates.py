from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.receipts.application.queries.get_receipt_activity_for_users.port import (
    ReceiptActivityForUsersReader,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.query import (
    GetReceiptActivityForUsersQuery,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.result import (
    ReceiptActivity,
    ReceiptActivityPage,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.port import (
    ReceiptsExpiringOnReader,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.query import (
    ListReceiptsExpiringOnQuery,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.result import (
    ExpiringReceipt,
    ExpiringReceiptsPage,
)
from app.modules.receipts.infrastructure.persistence import orm


@dataclass(frozen=True, slots=True)
class _ReceiptActivityAggregate:
    receipt_count: int
    last_receipt_created_at: datetime


class SqlAlchemyExpiringReceiptsReader(ReceiptsExpiringOnReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_receipts_expiring_on(
        self,
        *,
        query: ListReceiptsExpiringOnQuery,
    ) -> ExpiringReceiptsPage:
        target_expires_on = query.target_date + timedelta(days=query.offset_days)
        conditions = [
            orm.Receipt.expires_on == target_expires_on,
            orm.Receipt.created_at < query.observed_before,
        ]
        if query.cursor_receipt_id is not None:
            conditions.append(orm.Receipt.id > query.cursor_receipt_id)

        records = tuple(
            await self._session.scalars(
                select(orm.Receipt)
                .where(*conditions)
                .order_by(orm.Receipt.id.asc())
                .limit(query.limit + 1)
            )
        )
        page_records = records[: query.limit]
        has_next = len(records) > query.limit
        return ExpiringReceiptsPage(
            receipts=tuple(_expiring_receipt(record, query=query) for record in page_records),
            next_cursor_receipt_id=page_records[-1].id if has_next and page_records else None,
            has_next=has_next,
            limit=query.limit,
        )


class SqlAlchemyReceiptActivityForUsersReader(ReceiptActivityForUsersReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_receipt_activity_for_users(
        self,
        *,
        query: GetReceiptActivityForUsersQuery,
    ) -> ReceiptActivityPage:
        user_ids = _pageable_user_ids(query)
        if not user_ids:
            return ReceiptActivityPage(
                activities=(),
                next_cursor_user_id=None,
                has_next=False,
                limit=query.limit,
            )

        aggregates = await _activity_aggregates(
            session=self._session,
            user_ids=user_ids,
            observed_before=query.observed_before,
        )
        activities = tuple(
            activity
            for user_id in user_ids
            if (
                activity := _receipt_activity(
                    user_id=user_id,
                    aggregate=aggregates.get(user_id),
                    recent_since=query.recent_since,
                )
            )
            is not None
        )
        page_activities = activities[: query.limit]
        has_next = len(activities) > query.limit
        return ReceiptActivityPage(
            activities=page_activities,
            next_cursor_user_id=(
                page_activities[-1].user_id if has_next and page_activities else None
            ),
            has_next=has_next,
            limit=query.limit,
        )


def _expiring_receipt(
    record: orm.Receipt,
    *,
    query: ListReceiptsExpiringOnQuery,
) -> ExpiringReceipt:
    return ExpiringReceipt(
        user_id=record.user_id,
        receipt_id=record.id,
        item_name=record.item_name,
        sub_category=record.sub_category,
        expires_on=record.expires_on,
        created_at=record.created_at,
    )


def _pageable_user_ids(query: GetReceiptActivityForUsersQuery) -> tuple[UUID, ...]:
    return tuple(
        user_id
        for user_id in sorted(set(query.user_ids))
        if query.cursor_user_id is None or user_id > query.cursor_user_id
    )


async def _activity_aggregates(
    *,
    session: AsyncSession,
    user_ids: tuple[UUID, ...],
    observed_before: datetime,
) -> dict[UUID, _ReceiptActivityAggregate]:
    rows = await session.execute(
        select(
            orm.Receipt.user_id,
            func.count(orm.Receipt.id),
            func.max(orm.Receipt.created_at),
        )
        .where(
            orm.Receipt.user_id.in_(user_ids),
            orm.Receipt.created_at < observed_before,
        )
        .group_by(orm.Receipt.user_id)
    )
    return {
        user_id: _ReceiptActivityAggregate(
            receipt_count=receipt_count,
            last_receipt_created_at=last_receipt_created_at,
        )
        for user_id, receipt_count, last_receipt_created_at in rows.tuples()
    }


def _receipt_activity(
    *,
    user_id: UUID,
    aggregate: _ReceiptActivityAggregate | None,
    recent_since: datetime | None,
) -> ReceiptActivity | None:
    if aggregate is None:
        return ReceiptActivity(
            user_id=user_id,
            last_receipt_created_at=None,
            receipt_count=0,
            cursor_user_id=user_id,
        )

    if recent_since is not None and aggregate.last_receipt_created_at >= recent_since:
        return None

    return ReceiptActivity(
        user_id=user_id,
        last_receipt_created_at=aggregate.last_receipt_created_at,
        receipt_count=aggregate.receipt_count,
        cursor_user_id=user_id,
    )
