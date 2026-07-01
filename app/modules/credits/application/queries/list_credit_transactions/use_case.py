from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from app.core.domain.exceptions import DomainError
from app.modules.credits.application.ports.credit_repository import (
    CreditRepository,
    CreditTransactionCursor,
    CreditTransactionListItem,
)
from app.modules.credits.application.queries.list_credit_transactions.query import (
    ListCreditTransactionsQuery,
)
from app.modules.credits.application.queries.list_credit_transactions.result import (
    CreditTransactionListPage,
)

_CURSOR_SEPARATOR: Final = "|"


class InvalidCreditTransactionCursorError(DomainError):
    def __init__(self) -> None:
        super().__init__("크레딧 내역 cursor가 올바르지 않습니다.")


class ListCreditTransactionsQueryUseCase:
    def __init__(self, *, credit_repository: CreditRepository) -> None:
        self._credit_repository = credit_repository

    async def execute(self, query: ListCreditTransactionsQuery) -> CreditTransactionListPage:
        result = await self._credit_repository.list_transactions(
            user_id=query.user_id,
            cursor=_parse_cursor(query.cursor),
            limit=query.limit,
        )
        return CreditTransactionListPage(
            transactions=result.transactions,
            next_cursor=_next_cursor(result.transactions) if result.has_next else None,
            has_next=result.has_next,
            limit=query.limit,
            total_count=result.total_count,
        )


def _parse_cursor(cursor: str | None) -> CreditTransactionCursor | None:
    if cursor is None:
        return None

    parts = cursor.split(_CURSOR_SEPARATOR)
    if len(parts) != 2:
        raise InvalidCreditTransactionCursorError()

    try:
        created_at = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
        transaction_id = UUID(parts[1])
    except ValueError as exc:
        raise InvalidCreditTransactionCursorError from exc

    if created_at.tzinfo is None:
        raise InvalidCreditTransactionCursorError()

    return CreditTransactionCursor(created_at=created_at, transaction_id=transaction_id)


def _next_cursor(transactions: tuple[CreditTransactionListItem, ...]) -> str | None:
    if not transactions:
        return None

    last_transaction = transactions[-1]
    created_at = last_transaction.created_at.astimezone(UTC)
    created_at_text = created_at.isoformat().replace("+00:00", "Z")
    return f"{created_at_text}{_CURSOR_SEPARATOR}{last_transaction.transaction_id}"
