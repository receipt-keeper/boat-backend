import base64
import binascii
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, assert_never
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.receipts.application.ports.receipt_repository import (
    ReceiptListPage,
    ReceiptRepository,
)
from app.modules.receipts.application.queries.list_receipts.query import ListReceiptsQuery
from app.modules.receipts.application.read_models.receipt import ReceiptReadModel
from app.modules.receipts.domain.model import Receipt
from app.modules.receipts.domain.value_objects import ReceiptSort, ReceiptStatusFilter
from app.modules.receipts.infrastructure.persistence import mapper, orm


@dataclass(frozen=True, slots=True)
class _ReceiptCursor:
    sort: ReceiptSort
    value: date | datetime
    receipt_id: UUID


class SqlAlchemyReceiptRepository(ReceiptRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, receipt: Receipt) -> Receipt:
        record = mapper.receipt_to_record(receipt)
        self._session.add(record)
        for file_id in receipt.receipt_file_ids:
            self._session.add(mapper.attachment_to_record(receipt_id=receipt.id, file_id=file_id))
        await self._session.flush()
        return receipt

    async def list_by_user(self, *, query: ListReceiptsQuery) -> ReceiptListPage:
        conditions = _list_conditions(query)
        cursor = _decode_cursor(query.cursor, sort=query.sort)
        cursor_condition = _cursor_condition(query.sort, cursor)
        if cursor_condition is not None:
            conditions.append(cursor_condition)

        total_count = (
            await self._session.scalar(
                select(func.count()).select_from(orm.Receipt).where(*_list_conditions(query))
            )
            or 0
        )
        records = tuple(
            await self._session.scalars(
                select(orm.Receipt)
                .where(*conditions)
                .order_by(*_list_order_by(query.sort))
                .limit(query.limit + 1)
            )
        )
        page_records = records[: query.limit]
        receipts = await self._records_to_read_models(page_records)
        has_next = len(records) > query.limit
        return ReceiptListPage(
            receipts=receipts,
            total_count=total_count,
            next_cursor=(
                _encode_cursor(sort=query.sort, record=page_records[-1])
                if has_next and page_records
                else None
            ),
            has_next=has_next,
            limit=query.limit,
        )

    async def find_by_id_for_user(
        self,
        *,
        receipt_id: UUID,
        user_id: UUID,
    ) -> ReceiptReadModel | None:
        record = await self._find_record_by_id_for_user(
            receipt_id=receipt_id,
            user_id=user_id,
        )
        if record is None:
            return None
        return await self._record_to_read_model(record)

    async def update(self, *, receipt: Receipt) -> ReceiptReadModel | None:
        record = await self._find_record_by_id_for_user(
            receipt_id=receipt.id,
            user_id=receipt.user_id,
        )
        if record is None:
            return None

        record.item_name = receipt.item_name.value
        record.brand_name = receipt.brand_name
        record.payment_location = receipt.payment_location
        record.payment_date = receipt.payment_date.value
        record.total_amount = None if receipt.total_amount is None else receipt.total_amount.value
        record.period_months = receipt.period_months.value
        record.expires_on = receipt.expires_on
        record.category = receipt.category
        record.memo = receipt.memo
        record.requires_physical_receipt = receipt.requires_physical_receipt

        await self._session.execute(
            delete(orm.ReceiptAttachment).where(orm.ReceiptAttachment.receipt_id == receipt.id)
        )
        for file_id in receipt.receipt_file_ids:
            self._session.add(mapper.attachment_to_record(receipt_id=receipt.id, file_id=file_id))
        await self._session.flush()
        return await self._record_to_read_model(record)

    async def delete_by_id_for_user(self, *, receipt_id: UUID, user_id: UUID) -> bool:
        record = await self._find_record_by_id_for_user(
            receipt_id=receipt_id,
            user_id=user_id,
        )
        if record is None:
            return False
        await self._session.delete(record)
        await self._session.flush()
        return True

    async def _find_record_by_id_for_user(
        self,
        *,
        receipt_id: UUID,
        user_id: UUID,
    ) -> orm.Receipt | None:
        return await self._session.scalar(
            select(orm.Receipt).where(
                orm.Receipt.id == receipt_id,
                orm.Receipt.user_id == user_id,
            )
        )

    async def _record_to_read_model(self, record: orm.Receipt) -> ReceiptReadModel:
        receipt_file_ids = await self._file_ids_for_receipt(record.id)
        return mapper.record_to_read_model(record, receipt_file_ids=receipt_file_ids)

    async def _records_to_read_models(
        self,
        records: Iterable[orm.Receipt],
    ) -> tuple[ReceiptReadModel, ...]:
        records_by_id = {record.id: record for record in records}
        receipt_file_ids = await self._file_ids_by_receipt_id(records_by_id)
        return tuple(
            mapper.record_to_read_model(
                record,
                receipt_file_ids=tuple(receipt_file_ids[record.id]),
            )
            for record in records_by_id.values()
        )

    async def _file_ids_for_receipt(self, receipt_id: UUID) -> tuple[UUID, ...]:
        result = await self._session.scalars(
            select(orm.ReceiptAttachment.file_id)
            .where(orm.ReceiptAttachment.receipt_id == receipt_id)
            .order_by(orm.ReceiptAttachment.file_id.asc())
        )
        return tuple(result)

    async def _file_ids_by_receipt_id(
        self,
        records_by_id: dict[UUID, orm.Receipt],
    ) -> dict[UUID, list[UUID]]:
        file_ids_by_receipt_id: dict[UUID, list[UUID]] = defaultdict(list)
        if not records_by_id:
            return file_ids_by_receipt_id

        result = await self._session.execute(
            select(orm.ReceiptAttachment.receipt_id, orm.ReceiptAttachment.file_id)
            .where(orm.ReceiptAttachment.receipt_id.in_(tuple(records_by_id)))
            .order_by(
                orm.ReceiptAttachment.receipt_id.asc(),
                orm.ReceiptAttachment.file_id.asc(),
            )
        )
        for receipt_id, file_id in result:
            file_ids_by_receipt_id[receipt_id].append(file_id)
        return file_ids_by_receipt_id


def _list_conditions(query: ListReceiptsQuery) -> list[Any]:
    today = date.today()
    conditions: list[Any] = [orm.Receipt.user_id == query.user_id]
    match query.status:
        case ReceiptStatusFilter.ALL:
            pass
        case ReceiptStatusFilter.ACTIVE:
            conditions.append(orm.Receipt.expires_on > today + timedelta(days=30))
        case ReceiptStatusFilter.EXPIRING:
            conditions.append(orm.Receipt.expires_on.between(today, today + timedelta(days=30)))
        case ReceiptStatusFilter.EXPIRED:
            conditions.append(orm.Receipt.expires_on < today)

    if query.category is not None:
        conditions.append(orm.Receipt.category == query.category)
    if query.q is not None:
        escaped_keyword = _escape_like_keyword(query.q)
        pattern = f"%{escaped_keyword}%"
        conditions.append(
            or_(
                orm.Receipt.item_name.ilike(pattern, escape="\\"),
                orm.Receipt.brand_name.ilike(pattern, escape="\\"),
                orm.Receipt.payment_location.ilike(pattern, escape="\\"),
                orm.Receipt.memo.ilike(pattern, escape="\\"),
            )
        )
    return conditions


def _escape_like_keyword(keyword: str) -> str:
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _list_order_by(sort: ReceiptSort) -> tuple[Any, ...]:
    match sort:
        case ReceiptSort.RECENT:
            return (orm.Receipt.created_at.desc(), orm.Receipt.id.desc())
        case ReceiptSort.EXPIRES_ON:
            return (orm.Receipt.expires_on.asc(), orm.Receipt.id.asc())
        case ReceiptSort.PURCHASE_DATE:
            return (orm.Receipt.payment_date.desc(), orm.Receipt.id.desc())
        case unreachable:
            assert_never(unreachable)


def _cursor_condition(sort: ReceiptSort, cursor: _ReceiptCursor | None) -> Any | None:
    if cursor is None:
        return None

    match sort:
        case ReceiptSort.RECENT:
            return or_(
                orm.Receipt.created_at < cursor.value,
                and_(orm.Receipt.created_at == cursor.value, orm.Receipt.id < cursor.receipt_id),
            )
        case ReceiptSort.EXPIRES_ON:
            return or_(
                orm.Receipt.expires_on > cursor.value,
                and_(orm.Receipt.expires_on == cursor.value, orm.Receipt.id > cursor.receipt_id),
            )
        case ReceiptSort.PURCHASE_DATE:
            return or_(
                orm.Receipt.payment_date < cursor.value,
                and_(orm.Receipt.payment_date == cursor.value, orm.Receipt.id < cursor.receipt_id),
            )
        case unreachable:
            assert_never(unreachable)


def _encode_cursor(*, sort: ReceiptSort, record: orm.Receipt) -> str:
    payload = {
        "sort": sort.value,
        "value": _cursor_value(sort, record).isoformat(),
        "id": str(record.id),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return encoded.rstrip("=")


def _decode_cursor(cursor: str | None, *, sort: ReceiptSort) -> _ReceiptCursor | None:
    if cursor is None:
        return None

    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_cursor).decode("utf-8"))
        cursor_sort = ReceiptSort(payload["sort"])
        if cursor_sort != sort:
            raise ValueError("cursor sort mismatch")

        return _ReceiptCursor(
            sort=cursor_sort,
            value=_parse_cursor_value(sort=cursor_sort, value=payload["value"]),
            receipt_id=UUID(payload["id"]),
        )
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exception:
        raise ValidationError(
            [ErrorDetail(field="cursor", message="유효하지 않은 커서입니다.")]
        ) from exception


def _cursor_value(sort: ReceiptSort, record: orm.Receipt) -> date | datetime:
    match sort:
        case ReceiptSort.RECENT:
            return record.created_at
        case ReceiptSort.EXPIRES_ON:
            return record.expires_on
        case ReceiptSort.PURCHASE_DATE:
            return record.payment_date
        case unreachable:
            assert_never(unreachable)


def _parse_cursor_value(*, sort: ReceiptSort, value: str) -> date | datetime:
    match sort:
        case ReceiptSort.RECENT:
            return datetime.fromisoformat(value)
        case ReceiptSort.EXPIRES_ON | ReceiptSort.PURCHASE_DATE:
            return date.fromisoformat(value)
        case unreachable:
            assert_never(unreachable)
