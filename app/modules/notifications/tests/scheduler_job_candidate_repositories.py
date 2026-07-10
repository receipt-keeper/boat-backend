from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

from app.core.application.unit_of_work import UnitOfWork
from app.modules.receipts.application.ports.receipt_repository import (
    ReceiptListPage,
    ReceiptRegistrationActivityCandidate,
    ReceiptRegistrationActivityPage,
    ReceiptRegistrationActivityQuery,
    ReceiptRepository,
    WarrantyNotificationCandidate,
    WarrantyNotificationCandidatePage,
    WarrantyNotificationCandidateQuery,
)
from app.modules.receipts.application.queries.list_receipts.query import ListReceiptsQuery
from app.modules.receipts.application.read_models.receipt import ReceiptReadModel
from app.modules.receipts.domain.model import Receipt
from app.modules.users.application.ports.user_repository import (
    CreateUserAccountState,
    ListUserNotificationCandidatesQuery,
    UserAccountState,
    UserNotificationCandidate,
    UserNotificationCandidateCursor,
    UserNotificationCandidatePage,
    UserRepository,
)
from app.modules.users.domain.model import User, UserSettings


class ReceiptRepositoryFake(ReceiptRepository):
    def __init__(
        self,
        *,
        warranty_candidates: tuple[WarrantyNotificationCandidate, ...],
        receipt_activity_candidates: tuple[ReceiptRegistrationActivityCandidate, ...],
    ) -> None:
        self._warranty_candidates = warranty_candidates
        self._receipt_activity_candidates = receipt_activity_candidates
        self.warranty_queries: list[WarrantyNotificationCandidateQuery] = []

    async def create(self, *, receipt: Receipt) -> ReceiptReadModel:
        raise NotImplementedError

    async def list_by_user(self, *, query: ListReceiptsQuery) -> ReceiptListPage:
        raise NotImplementedError

    async def find_by_id_for_user(
        self,
        *,
        receipt_id: UUID,
        user_id: UUID,
    ) -> ReceiptReadModel | None:
        raise NotImplementedError

    async def update(self, *, receipt: Receipt) -> ReceiptReadModel | None:
        raise NotImplementedError

    async def delete_by_id_for_user(self, *, receipt_id: UUID, user_id: UUID) -> bool:
        raise NotImplementedError

    async def list_warranty_notification_candidates(
        self,
        *,
        query: WarrantyNotificationCandidateQuery,
    ) -> WarrantyNotificationCandidatePage:
        self.warranty_queries.append(query)
        candidates = tuple(
            candidate
            for candidate in self._warranty_candidates
            if candidate.expires_on == query.target_date + timedelta(days=query.offset_days)
        )
        return WarrantyNotificationCandidatePage(
            candidates=candidates[: query.limit],
            next_cursor_receipt_id=None,
            has_next=False,
            limit=query.limit,
        )

    async def list_receipt_registration_activity_candidates(
        self,
        *,
        query: ReceiptRegistrationActivityQuery,
    ) -> ReceiptRegistrationActivityPage:
        candidates = tuple(
            candidate
            for candidate in self._receipt_activity_candidates
            if candidate.user_id in query.user_ids
        )
        return ReceiptRegistrationActivityPage(
            candidates=candidates[: query.limit],
            next_cursor_user_id=None,
            has_next=False,
            limit=query.limit,
        )


class UserRepositoryFake(UserRepository):
    def __init__(self, candidates: tuple[UserNotificationCandidate, ...]) -> None:
        self._candidates = candidates

    async def create(self, *, name: str | None, email: str | None) -> User:
        raise NotImplementedError

    async def delete_by_id(self, *, user_id: UUID) -> None:
        raise NotImplementedError

    async def find_account_state(self, *, user_id: UUID) -> UserAccountState | None:
        raise NotImplementedError

    async def create_account_state(self, *, state: CreateUserAccountState) -> UserAccountState:
        raise NotImplementedError

    async def update_settings(self, *, settings: UserSettings) -> UserSettings:
        raise NotImplementedError

    async def update_profile_image_url(
        self,
        *,
        user_id: UUID,
        profile_image_url: str | None,
    ) -> User:
        raise NotImplementedError

    async def delete_account_state(self, *, user_id: UUID) -> None:
        raise NotImplementedError

    async def list_notification_candidates(
        self,
        *,
        query: ListUserNotificationCandidatesQuery,
    ) -> UserNotificationCandidatePage:
        next_cursor = (
            UserNotificationCandidateCursor(
                created_at=self._candidates[-1].cursor_created_at,
                user_id=self._candidates[-1].cursor_id,
            )
            if len(self._candidates) > query.batch_size
            else None
        )
        return UserNotificationCandidatePage(
            candidates=self._candidates[: query.batch_size],
            next_cursor=next_cursor,
        )


class UnitOfWorkFake(UnitOfWork):
    def __init__(self, rollback_hook: Callable[[], None] | None = None) -> None:
        self.commits = 0
        self.rollbacks = 0
        self._rollback_hook = rollback_hook

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self._rollback_hook is not None:
            self._rollback_hook()
