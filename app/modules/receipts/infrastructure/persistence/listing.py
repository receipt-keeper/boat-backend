import base64
import binascii
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, assert_never, cast
from uuid import UUID

from sqlalchemy import and_, or_

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.receipts.application.queries.list_receipts.query import ListReceiptsQuery
from app.modules.receipts.domain.value_objects import ReceiptSort, ReceiptStatusFilter
from app.modules.receipts.infrastructure.persistence import orm


@dataclass(frozen=True, slots=True)
class ReceiptCursor:
    sort: ReceiptSort
    value: date | datetime | str
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class _InvalidReceiptCursorError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


def list_conditions(query: ListReceiptsQuery) -> list[Any]:
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
        case unreachable:
            assert_never(unreachable)

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


def cursor_condition(sort: ReceiptSort, cursor: ReceiptCursor | None) -> Any | None:
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
        case ReceiptSort.TITLE:
            title = cast(str, cursor.value)
            return or_(
                orm.Receipt.item_name > title,
                and_(orm.Receipt.item_name == title, orm.Receipt.id > cursor.receipt_id),
            )
        case unreachable:
            assert_never(unreachable)


def list_order_by(sort: ReceiptSort) -> tuple[Any, ...]:
    match sort:
        case ReceiptSort.RECENT:
            return (orm.Receipt.created_at.desc(), orm.Receipt.id.desc())
        case ReceiptSort.EXPIRES_ON:
            return (orm.Receipt.expires_on.asc(), orm.Receipt.id.asc())
        case ReceiptSort.PURCHASE_DATE:
            return (orm.Receipt.payment_date.desc(), orm.Receipt.id.desc())
        case ReceiptSort.TITLE:
            return (orm.Receipt.item_name.asc(), orm.Receipt.id.asc())
        case unreachable:
            assert_never(unreachable)


def encode_cursor(*, sort: ReceiptSort, record: orm.Receipt) -> str:
    cursor_value = _cursor_value(sort, record)
    payload = {
        "sort": sort.value,
        "value": cursor_value if isinstance(cursor_value, str) else cursor_value.isoformat(),
        "id": str(record.id),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return encoded.rstrip("=")


def decode_cursor(cursor: str | None, *, sort: ReceiptSort) -> ReceiptCursor | None:
    if cursor is None:
        return None

    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_cursor).decode("utf-8"))
        cursor_sort = ReceiptSort(payload["sort"])
        if cursor_sort != sort:
            raise _InvalidReceiptCursorError(reason="cursor sort mismatch")
        cursor_receipt_id = payload["id"]
        if not isinstance(cursor_receipt_id, str):
            raise _InvalidReceiptCursorError(reason="cursor id must be a string")

        return ReceiptCursor(
            sort=cursor_sort,
            value=_parse_cursor_value(sort=cursor_sort, value=payload["value"]),
            receipt_id=UUID(cursor_receipt_id),
        )
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        _InvalidReceiptCursorError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exception:
        raise ValidationError(
            [ErrorDetail(field="cursor", message="유효하지 않은 커서입니다.")]
        ) from exception


def _escape_like_keyword(keyword: str) -> str:
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _cursor_value(sort: ReceiptSort, record: orm.Receipt) -> date | datetime | str:
    match sort:
        case ReceiptSort.RECENT:
            return record.created_at
        case ReceiptSort.EXPIRES_ON:
            return record.expires_on
        case ReceiptSort.PURCHASE_DATE:
            return record.payment_date
        case ReceiptSort.TITLE:
            return record.item_name
        case unreachable:
            assert_never(unreachable)


def _parse_cursor_value(*, sort: ReceiptSort, value: str) -> date | datetime | str:
    match sort:
        case ReceiptSort.RECENT:
            return datetime.fromisoformat(value)
        case ReceiptSort.EXPIRES_ON | ReceiptSort.PURCHASE_DATE:
            return date.fromisoformat(value)
        case ReceiptSort.TITLE:
            if not isinstance(value, str):
                raise _InvalidReceiptCursorError(reason="title cursor value must be a string")
            return value
        case unreachable:
            assert_never(unreachable)
