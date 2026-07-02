from dataclasses import dataclass

from app.modules.credits.application.ports.credit_repository import CreditTransactionListItem


@dataclass(frozen=True, slots=True)
class CreditTransactionListPage:
    transactions: tuple[CreditTransactionListItem, ...]
    next_cursor: str | None
    has_next: bool
    limit: int
    total_count: int
