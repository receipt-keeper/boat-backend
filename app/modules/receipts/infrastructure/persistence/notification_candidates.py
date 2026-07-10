from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.receipts.application.ports.receipt_repository import (
    ReceiptRegistrationActivityCandidate,
    ReceiptRegistrationActivityPage,
    ReceiptRegistrationActivityQuery,
    WarrantyNotificationCandidate,
    WarrantyNotificationCandidatePage,
    WarrantyNotificationCandidateQuery,
)
from app.modules.receipts.infrastructure.persistence import orm


@dataclass(frozen=True, slots=True)
class _ReceiptActivityAggregate:
    receipt_count: int
    last_receipt_created_at: datetime


async def list_warranty_notification_candidates(
    *,
    session: AsyncSession,
    query: WarrantyNotificationCandidateQuery,
) -> WarrantyNotificationCandidatePage:
    target_expires_on = query.target_date + timedelta(days=query.offset_days)
    conditions = [orm.Receipt.expires_on == target_expires_on]
    if query.cursor_receipt_id is not None:
        conditions.append(orm.Receipt.id > query.cursor_receipt_id)

    records = tuple(
        await session.scalars(
            select(orm.Receipt)
            .where(*conditions)
            .order_by(orm.Receipt.id.asc())
            .limit(query.limit + 1)
        )
    )
    page_records = records[: query.limit]
    has_next = len(records) > query.limit
    return WarrantyNotificationCandidatePage(
        candidates=tuple(_warranty_candidate(record, query=query) for record in page_records),
        next_cursor_receipt_id=page_records[-1].id if has_next and page_records else None,
        has_next=has_next,
        limit=query.limit,
    )


async def list_receipt_registration_activity_candidates(
    *,
    session: AsyncSession,
    query: ReceiptRegistrationActivityQuery,
) -> ReceiptRegistrationActivityPage:
    user_ids = _pageable_user_ids(query)
    if not user_ids:
        return ReceiptRegistrationActivityPage(
            candidates=(),
            next_cursor_user_id=None,
            has_next=False,
            limit=query.limit,
        )

    aggregates = await _activity_aggregates(session=session, user_ids=user_ids)
    recent_cutoff = datetime.combine(query.target_date, time.min, tzinfo=UTC) - timedelta(
        days=query.recent_days
    )
    candidates = tuple(
        candidate
        for user_id in user_ids
        if (
            candidate := _activity_candidate(
                user_id=user_id,
                aggregate=aggregates.get(user_id),
                recent_cutoff=recent_cutoff,
            )
        )
        is not None
    )
    page_candidates = candidates[: query.limit]
    has_next = len(candidates) > query.limit
    return ReceiptRegistrationActivityPage(
        candidates=page_candidates,
        next_cursor_user_id=page_candidates[-1].user_id if has_next and page_candidates else None,
        has_next=has_next,
        limit=query.limit,
    )


def _warranty_candidate(
    record: orm.Receipt,
    *,
    query: WarrantyNotificationCandidateQuery,
) -> WarrantyNotificationCandidate:
    return WarrantyNotificationCandidate(
        user_id=record.user_id,
        receipt_id=record.id,
        item_name=record.item_name,
        expires_on=record.expires_on,
        days_until_expiry=(record.expires_on - query.target_date).days,
    )


def _pageable_user_ids(query: ReceiptRegistrationActivityQuery) -> tuple[UUID, ...]:
    return tuple(
        user_id
        for user_id in sorted(set(query.user_ids))
        if query.cursor_user_id is None or user_id > query.cursor_user_id
    )


async def _activity_aggregates(
    *,
    session: AsyncSession,
    user_ids: tuple[UUID, ...],
) -> dict[UUID, _ReceiptActivityAggregate]:
    rows = await session.execute(
        select(
            orm.Receipt.user_id,
            func.count(orm.Receipt.id),
            func.max(orm.Receipt.created_at),
        )
        .where(orm.Receipt.user_id.in_(user_ids))
        .group_by(orm.Receipt.user_id)
    )
    return {
        user_id: _ReceiptActivityAggregate(
            receipt_count=receipt_count,
            last_receipt_created_at=last_receipt_created_at,
        )
        for user_id, receipt_count, last_receipt_created_at in rows.tuples()
    }


def _activity_candidate(
    *,
    user_id: UUID,
    aggregate: _ReceiptActivityAggregate | None,
    recent_cutoff: datetime,
) -> ReceiptRegistrationActivityCandidate | None:
    if aggregate is None:
        return ReceiptRegistrationActivityCandidate(
            user_id=user_id,
            last_receipt_created_at=None,
            receipt_count=0,
            cursor_user_id=user_id,
        )

    if aggregate.last_receipt_created_at >= recent_cutoff:
        return None

    return ReceiptRegistrationActivityCandidate(
        user_id=user_id,
        last_receipt_created_at=aggregate.last_receipt_created_at,
        receipt_count=aggregate.receipt_count,
        cursor_user_id=user_id,
    )
