from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from app.modules.users.domain.model import User, UserEntitlement, UserPushToken, UserSettings


@dataclass(frozen=True, slots=True)
class UserAccountState:
    user: User
    settings: UserSettings
    entitlement: UserEntitlement
    push_tokens: tuple[UserPushToken, ...]


@dataclass(frozen=True, slots=True)
class CreateUserAccountState:
    user: User
    settings: UserSettings
    entitlement: UserEntitlement


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
    async def upsert_push_token(self, *, push_token: UserPushToken) -> UserPushToken:
        raise NotImplementedError

    @abstractmethod
    async def delete_push_token(self, *, user_id: UUID, device_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_account_state(self, *, user_id: UUID) -> None:
        raise NotImplementedError
