from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.users.domain.model import User


class UserRepository(ABC):
    @abstractmethod
    async def create(self, *, name: str | None, email: str | None) -> User:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_id(self, *, user_id: UUID) -> None:
        raise NotImplementedError
