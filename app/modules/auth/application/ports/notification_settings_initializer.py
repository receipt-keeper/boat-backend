from abc import ABC, abstractmethod
from uuid import UUID


class NotificationSettingsInitializer(ABC):
    @abstractmethod
    async def initialize(self, *, user_id: UUID, marketing_consent: bool) -> None:
        raise NotImplementedError
