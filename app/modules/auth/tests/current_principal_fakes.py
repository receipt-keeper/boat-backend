from datetime import datetime
from uuid import UUID

from app.modules.auth.application.ports.credential_repository import (
    ActiveSessionChecker,
    CredentialRepository,
    SessionCredential,
)
from app.modules.auth.domain.model import ExternalIdentity, UserCredential

TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_CREDENTIALS_ID = UUID("00000000-0000-0000-0000-000000000002")
TEST_SESSION_ID = UUID("00000000-0000-0000-0000-000000000003")


class CredentialStateRepository(CredentialRepository):
    def __init__(self, *, active: bool) -> None:
        self._active = active

    async def find_by_external_identity(
        self,
        *,
        identity: ExternalIdentity,
    ) -> UserCredential | None:
        assert identity
        return None

    async def find_by_verified_email(self, *, canonical_email: str) -> UserCredential | None:
        assert canonical_email
        return None

    async def create_for_external_identity(
        self,
        *,
        identity: ExternalIdentity,
        user_id: UUID,
        logged_in_at: datetime,
    ) -> UserCredential:
        assert identity
        assert user_id
        assert logged_in_at
        raise AssertionError("create must not be called")

    async def record_login(
        self,
        *,
        credentials_id: UUID,
        logged_in_at: datetime,
    ) -> UserCredential:
        assert credentials_id
        assert logged_in_at
        raise AssertionError("record_login must not be called")

    async def find_credential_by_user_id(self, *, user_id: UUID) -> UserCredential | None:
        assert user_id
        raise AssertionError("find_credential_by_user_id must not be called")

    async def attach_external_identity(
        self,
        *,
        credentials_id: UUID,
        identity: ExternalIdentity,
    ) -> None:
        assert credentials_id
        assert identity
        raise AssertionError("attach_external_identity must not be called")

    async def create_session(self, *, credentials_id: UUID) -> UUID:
        assert credentials_id
        raise AssertionError("create_session must not be called")

    async def save_refresh_token(
        self,
        *,
        credentials_id: UUID,
        session_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        assert credentials_id
        assert session_id
        assert token_hash
        assert expires_at
        raise AssertionError("save_refresh_token must not be called")

    async def rotate_refresh_token(
        self,
        *,
        token_hash: str,
        new_token_hash: str,
        expires_at: datetime,
    ) -> SessionCredential:
        assert token_hash
        assert new_token_hash
        assert expires_at
        raise AssertionError("rotate_refresh_token must not be called")

    async def revoke_session_by_refresh_token(self, *, token_hash: str) -> None:
        assert token_hash
        raise AssertionError("revoke_session_by_refresh_token must not be called")

    async def exists_active_credential(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> bool:
        assert user_id == TEST_USER_ID
        assert credentials_id == TEST_CREDENTIALS_ID
        return self._active

    async def exists_active_session(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
        session_id: UUID,
    ) -> bool:
        assert user_id == TEST_USER_ID
        assert credentials_id == TEST_CREDENTIALS_ID
        assert session_id == TEST_SESSION_ID
        return self._active

    async def delete_account_auth_state(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> None:
        assert user_id
        assert credentials_id
        raise AssertionError("delete_account_auth_state must not be called")


class StaticActiveSessionChecker(ActiveSessionChecker):
    def __init__(self, repository: CredentialRepository) -> None:
        self._repository = repository

    async def exists_active_session(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
        session_id: UUID,
    ) -> bool:
        return await self._repository.exists_active_session(
            user_id=user_id,
            credentials_id=credentials_id,
            session_id=session_id,
        )
