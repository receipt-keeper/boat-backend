from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.modules.auth.domain.model import ExternalIdentity, UserCredential


class CredentialRepository(ABC):
    @abstractmethod
    async def find_by_external_identity(
        self,
        *,
        identity: ExternalIdentity,
    ) -> UserCredential | None:
        raise NotImplementedError

    @abstractmethod
    async def create_for_external_identity(
        self,
        *,
        identity: ExternalIdentity,
        user_id: UUID,
        logged_in_at: datetime,
    ) -> UserCredential:
        raise NotImplementedError

    @abstractmethod
    async def record_login(
        self,
        *,
        credentials_id: UUID,
        logged_in_at: datetime,
    ) -> UserCredential:
        raise NotImplementedError

    @abstractmethod
    async def save_refresh_token(
        self,
        *,
        credentials_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rotate_refresh_token(
        self,
        *,
        token_hash: str,
        new_token_hash: str,
        expires_at: datetime,
    ) -> UserCredential:
        raise NotImplementedError

    @abstractmethod
    async def revoke_refresh_token(self, *, token_hash: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def exists_active_credential(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete_account_auth_state(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> None:
        raise NotImplementedError


class CredentialRepositoryProvider(ABC):
    @abstractmethod
    def get(self) -> CredentialRepository:
        raise NotImplementedError
