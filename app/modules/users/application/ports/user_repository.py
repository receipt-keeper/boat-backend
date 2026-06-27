from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from app.modules.users.domain.model import User, UserSettings


@dataclass(frozen=True, slots=True)
class UserAccountState:
    user: User
    settings: UserSettings


@dataclass(frozen=True, slots=True)
class CreateUserAccountState:
    user: User
    settings: UserSettings


class UserRepository(ABC):
    @abstractmethod
    async def create(self, *, name: str | None, email: str | None) -> User:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_id(self, *, user_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def find_account_state(self, *, user_id: UUID) -> UserAccountState | None:
        raise NotImplementedError

    @abstractmethod
    async def create_account_state(self, *, state: CreateUserAccountState) -> UserAccountState:
        raise NotImplementedError

    @abstractmethod
    async def update_settings(self, *, settings: UserSettings) -> UserSettings:
        raise NotImplementedError

    @abstractmethod
    async def update_profile_image_url(
        self,
        *,
        user_id: UUID,
        profile_image_url: str | None,
    ) -> User:
        raise NotImplementedError

    @abstractmethod
    async def delete_account_state(self, *, user_id: UUID) -> None:
        raise NotImplementedError
