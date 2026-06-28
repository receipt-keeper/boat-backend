from uuid import UUID

from app.core.domain.exceptions import NotFoundError


class ReceiptNotFoundError(NotFoundError):
    def __init__(self, *, receipt_id: UUID) -> None:
        self.receipt_id = receipt_id
        super().__init__("영수증을 찾을 수 없습니다.")
