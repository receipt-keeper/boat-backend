from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from app.modules.notifications.domain.model import UserPushToken
from app.modules.notifications.domain.value_objects import DevicePlatform


class PushTokenRepository(ABC):
    @abstractmethod
    async def register(
        self,
        *,
        user_id: UUID,
        token: str,
        platform: DevicePlatform,
    ) -> UserPushToken:
        raise NotImplementedError

    @abstractmethod
    async def unregister(self, *, user_id: UUID, token: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_by_user(self, *, user_id: UUID) -> tuple[UserPushToken, ...]:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_tokens(self, *, tokens: Sequence[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_user_id(self, *, user_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_stale(self, *, older_than: datetime) -> int:
        raise NotImplementedError
