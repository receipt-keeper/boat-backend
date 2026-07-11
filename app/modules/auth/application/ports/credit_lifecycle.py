from abc import ABC, abstractmethod
from uuid import UUID


class CreditInitializer(ABC):
    @abstractmethod
    async def initialize(self, *, user_id: UUID, identity_hash: str) -> None:
        raise NotImplementedError


class CreditWithdrawalCleaner(ABC):
    @abstractmethod
    async def delete_account_state(self, *, user_id: UUID) -> None:
        raise NotImplementedError
