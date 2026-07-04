from abc import ABC, abstractmethod
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
