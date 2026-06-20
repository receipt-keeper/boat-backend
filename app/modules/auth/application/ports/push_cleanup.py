from abc import ABC, abstractmethod
from uuid import UUID


class PushCleanup(ABC):
    @abstractmethod
    async def cleanup_withdrawn_account(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> None:
        raise NotImplementedError
