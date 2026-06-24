from abc import ABC, abstractmethod
from uuid import UUID


class FileReferenceGuard(ABC):
    @abstractmethod
    async def ensure_not_referenced(self, *, file_id: UUID) -> None:
        raise NotImplementedError
