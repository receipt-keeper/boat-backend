from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.modules.notifications.domain.model import UserPushToken
from app.modules.notifications.domain.value_objects import DevicePlatform


class PushTokenRepository(ABC):
    @abstractmethod
    async def register(
        self,
        *,
        user_id: UUID,
        device_id: str,
        fcm_token: str,
        platform: DevicePlatform,
    ) -> UserPushToken:
        raise NotImplementedError

    @abstractmethod
    async def unregister(self, *, user_id: UUID, device_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_by_user(self, *, user_id: UUID) -> tuple[UserPushToken, ...]:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_fcm_tokens(self, *, fcm_tokens: Sequence[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_user_id(self, *, user_id: UUID) -> None:
        raise NotImplementedError
