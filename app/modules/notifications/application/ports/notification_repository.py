from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.notifications.domain.model import NotificationSettings, UserNotification


@dataclass(frozen=True, slots=True)
class NotificationListCursor:
    created_at: datetime
    notification_id: UUID


@dataclass(frozen=True, slots=True)
class NotificationListResult:
    notifications: tuple[UserNotification, ...]
    has_next: bool
    total_count: int


class NotificationRepository(ABC):
    @abstractmethod
    async def create(self, *, notification: UserNotification) -> UserNotification:
        raise NotImplementedError

    @abstractmethod
    async def list_by_user(
        self,
        *,
        user_id: UUID,
        cursor: NotificationListCursor | None,
        limit: int,
    ) -> NotificationListResult:
        raise NotImplementedError

    @abstractmethod
    async def find_by_id_for_user(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
    ) -> UserNotification | None:
        raise NotImplementedError

    @abstractmethod
    async def mark_read(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
        read_at: datetime,
    ) -> UserNotification | None:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_id_for_user(self, *, notification_id: UUID, user_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_settings(self, *, user_id: UUID) -> NotificationSettings:
        raise NotImplementedError

    @abstractmethod
    async def get_settings_for_update(self, *, user_id: UUID) -> NotificationSettings:
        raise NotImplementedError

    @abstractmethod
    async def update_settings(
        self,
        *,
        user_id: UUID,
        push_enabled: bool | None,
        marketing_consent: bool | None,
    ) -> NotificationSettings:
        raise NotImplementedError
