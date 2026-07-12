from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID


class CreditInitializer(ABC):
    @abstractmethod
    async def initialize(
        self,
        *,
        user_id: UUID,
        subject_handle: str,
        candidate_handles: Sequence[str],
    ) -> None:
        raise NotImplementedError


class CreditWithdrawalCleaner(ABC):
    @abstractmethod
    async def delete_account_state(
        self,
        *,
        user_id: UUID,
        candidate_handles: Sequence[str],
    ) -> None:
        raise NotImplementedError
