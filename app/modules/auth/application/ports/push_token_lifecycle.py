from abc import ABC, abstractmethod
from uuid import UUID


class PushTokenWithdrawalCleaner(ABC):
    @abstractmethod
    async def delete_account_state(self, *, user_id: UUID) -> None:
        raise NotImplementedError
