from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.users.domain.model import User, UserSettings

_INVALID_BATCH_SIZE = "사용자 후보 조회 batchSize가 올바르지 않습니다."
_INVALID_CURSOR = "사용자 후보 조회 cursor가 올바르지 않습니다."
_INVALID_CREATED_WINDOW = "사용자 후보 조회 createdAt 범위가 올바르지 않습니다."


@dataclass(frozen=True, slots=True)
class UserAccountState:
    user: User
    settings: UserSettings


@dataclass(frozen=True, slots=True)
class CreateUserAccountState:
    user: User
    settings: UserSettings


@dataclass(frozen=True, slots=True)
class UserNotificationCandidateCursor:
    created_at: datetime
    user_id: UUID

    def __post_init__(self) -> None:
        if not _is_aware_datetime(self.created_at):
            raise ValidationError([ErrorDetail(field="cursor", message=_INVALID_CURSOR)])
        if not isinstance(self.user_id, UUID):
            raise ValidationError([ErrorDetail(field="cursor", message=_INVALID_CURSOR)])


@dataclass(frozen=True, slots=True)
class ListUserNotificationCandidatesQuery:
    as_of: date
    batch_size: int
    cursor: UserNotificationCandidateCursor | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None

    def __post_init__(self) -> None:
        details: list[ErrorDetail] = []
        if self.batch_size < 1:
            details.append(ErrorDetail(field="batchSize", message=_INVALID_BATCH_SIZE))
        if self.created_after is not None and not _is_aware_datetime(self.created_after):
            details.append(ErrorDetail(field="createdAfter", message=_INVALID_CREATED_WINDOW))
        if self.created_before is not None and not _is_aware_datetime(self.created_before):
            details.append(ErrorDetail(field="createdBefore", message=_INVALID_CREATED_WINDOW))
        if (
            self.created_after is not None
            and self.created_before is not None
            and self.created_after >= self.created_before
        ):
            details.append(ErrorDetail(field="createdAt", message=_INVALID_CREATED_WINDOW))
        if details:
            raise ValidationError(details)


@dataclass(frozen=True, slots=True)
class UserNotificationCandidate:
    user_id: UUID
    created_at: datetime
    days_since_joined: int
    cursor_created_at: datetime
    cursor_id: UUID


@dataclass(frozen=True, slots=True)
class UserNotificationCandidatePage:
    candidates: tuple[UserNotificationCandidate, ...]
    next_cursor: UserNotificationCandidateCursor | None


class UserRepository(ABC):
    @abstractmethod
    async def create(self, *, name: str | None, email: str | None) -> User:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_id(self, *, user_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def find_account_state(self, *, user_id: UUID) -> UserAccountState | None:
        raise NotImplementedError

    @abstractmethod
    async def create_account_state(self, *, state: CreateUserAccountState) -> UserAccountState:
        raise NotImplementedError

    @abstractmethod
    async def update_settings(self, *, settings: UserSettings) -> UserSettings:
        raise NotImplementedError

    @abstractmethod
    async def update_profile_image_url(
        self,
        *,
        user_id: UUID,
        profile_image_url: str | None,
    ) -> User:
        raise NotImplementedError

    @abstractmethod
    async def delete_account_state(self, *, user_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_notification_candidates(
        self,
        *,
        query: ListUserNotificationCandidatesQuery,
    ) -> UserNotificationCandidatePage:
        raise NotImplementedError


def _is_aware_datetime(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None
