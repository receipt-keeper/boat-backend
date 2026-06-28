from dataclasses import dataclass

from app.modules.receipts.application.read_models.receipt import ReceiptReadModel


@dataclass(frozen=True, slots=True)
class ListReceiptsResult:
    receipts: tuple[ReceiptReadModel, ...]
    total_count: int
    next_cursor: str | None
    has_next: bool
    limit: int
