from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar

from app.core.http.responses import CursorPaginationResponse

ItemT = TypeVar("ItemT")


@dataclass(frozen=True, slots=True)
class CursorPage[ItemT]:
    items: list[ItemT]
    pagination: CursorPaginationResponse


def paginate_by_cursor[ItemT](
    items: Sequence[ItemT],
    *,
    cursor: str | None,
    limit: int,
    total_count: int | None = None,
) -> CursorPage[ItemT]:
    start = _decode_cursor(cursor)
    item_count = len(items)
    end = min(start + limit, item_count)
    has_next = end < item_count
    next_cursor = str(end) if has_next else None

    return CursorPage(
        items=list(items[start:end]),
        pagination=CursorPaginationResponse(
            nextCursor=next_cursor,
            hasNext=has_next,
            limit=limit,
            totalCount=total_count if total_count is not None else item_count,
        ),
    )


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None or not cursor.isdecimal():
        return 0
    return int(cursor)
