from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.receipts.application.queries.list_receipts.query import ListReceiptsQuery
from app.modules.receipts.application.read_models.receipt import ReceiptReadModel
from app.modules.receipts.domain.model import Receipt

_INVALID_WARRANTY_OFFSET_DAYS = "보증 알림 후보 조회 offsetDays가 올바르지 않습니다."
_INVALID_WARRANTY_BATCH_SIZE = "보증 알림 후보 조회 batchSize가 올바르지 않습니다."
_INVALID_ACTIVITY_BATCH_SIZE = "영수증 등록 활동 후보 조회 batchSize가 올바르지 않습니다."
_INVALID_ACTIVITY_RECENT_DAYS = "영수증 등록 활동 후보 조회 recentDays가 올바르지 않습니다."


@dataclass(frozen=True, slots=True)
class ReceiptListPage:
    receipts: tuple[ReceiptReadModel, ...]
    total_count: int
    next_cursor: str | None
    has_next: bool
    limit: int


@dataclass(frozen=True, slots=True)
class WarrantyNotificationCandidateQuery:
    target_date: date
    offset_days: int
    limit: int
    cursor_receipt_id: UUID | None = None

    def __post_init__(self) -> None:
        details: list[ErrorDetail] = []
        if self.offset_days < 0:
            details.append(ErrorDetail(field="offsetDays", message=_INVALID_WARRANTY_OFFSET_DAYS))
        if self.limit < 1:
            details.append(ErrorDetail(field="batchSize", message=_INVALID_WARRANTY_BATCH_SIZE))
        if details:
            raise ValidationError(details)


@dataclass(frozen=True, slots=True)
class WarrantyNotificationCandidate:
    user_id: UUID
    receipt_id: UUID
    item_name: str
    expires_on: date
    days_until_expiry: int


@dataclass(frozen=True, slots=True)
class WarrantyNotificationCandidatePage:
    candidates: tuple[WarrantyNotificationCandidate, ...]
    next_cursor_receipt_id: UUID | None
    has_next: bool
    limit: int


@dataclass(frozen=True, slots=True)
class ReceiptRegistrationActivityQuery:
    user_ids: tuple[UUID, ...]
    target_date: date
    limit: int
    recent_days: int
    cursor_user_id: UUID | None = None

    def __post_init__(self) -> None:
        details: list[ErrorDetail] = []
        if self.limit < 1:
            details.append(ErrorDetail(field="batchSize", message=_INVALID_ACTIVITY_BATCH_SIZE))
        if self.recent_days < 1:
            details.append(ErrorDetail(field="recentDays", message=_INVALID_ACTIVITY_RECENT_DAYS))
        if details:
            raise ValidationError(details)


@dataclass(frozen=True, slots=True)
class ReceiptRegistrationActivityCandidate:
    user_id: UUID
    last_receipt_created_at: datetime | None
    receipt_count: int
    cursor_user_id: UUID


@dataclass(frozen=True, slots=True)
class ReceiptRegistrationActivityPage:
    candidates: tuple[ReceiptRegistrationActivityCandidate, ...]
    next_cursor_user_id: UUID | None
    has_next: bool
    limit: int


class ReceiptRepository(ABC):
    @abstractmethod
    async def create(self, *, receipt: Receipt) -> ReceiptReadModel:
        raise NotImplementedError

    @abstractmethod
    async def list_by_user(self, *, query: ListReceiptsQuery) -> ReceiptListPage:
        raise NotImplementedError

    @abstractmethod
    async def find_by_id_for_user(
        self,
        *,
        receipt_id: UUID,
        user_id: UUID,
    ) -> ReceiptReadModel | None:
        raise NotImplementedError

    @abstractmethod
    async def update(self, *, receipt: Receipt) -> ReceiptReadModel | None:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_id_for_user(self, *, receipt_id: UUID, user_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def list_warranty_notification_candidates(
        self,
        *,
        query: WarrantyNotificationCandidateQuery,
    ) -> WarrantyNotificationCandidatePage:
        raise NotImplementedError

    @abstractmethod
    async def list_receipt_registration_activity_candidates(
        self,
        *,
        query: ReceiptRegistrationActivityQuery,
    ) -> ReceiptRegistrationActivityPage:
        raise NotImplementedError
