from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.modules.auth.application.constants import AUTHENTICATION_FAILED_MESSAGE
from app.modules.auth.application.login.use_case import LoginUseCase
from app.modules.auth.application.logout.use_case import LogoutUseCase
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.external_identity_login_synchronizer import (
    ExternalIdentityLoginSynchronizer,
)
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.application.ports.token_issuer import AccessTokenIssuer
from app.modules.auth.application.ports.user_provisioner import ProvisionedUser, UserProvisioner
from app.modules.auth.application.refresh.use_case import RefreshTokenUseCase
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity, UserCredential
from app.modules.auth.infrastructure.tokens.jwt import JwtAccessTokenService
from app.modules.auth.infrastructure.tokens.opaque_refresh_token import OpaqueRefreshTokenIssuer

TEST_SIGNING_KEY = "x" * 48


@dataclass
class FakeExternalIdentityVerifier(ExternalIdentityVerifier):
    identity: ExternalIdentity | None = None
    error: Exception | None = None

    async def verify(self, provider_token: str) -> ExternalIdentity:
        if self.error is not None:
            raise self.error
        if self.identity is None:
            raise AssertionError("identity or error is required")
        return self.identity


class FakeUserProvisioner(UserProvisioner):
    def __init__(self) -> None:
        self.provisioned: list[tuple[str | None, str | None]] = []

    async def provision(self, *, name: str | None, email: str | None) -> ProvisionedUser:
        self.provisioned.append((name, email))
        return ProvisionedUser(user_id=uuid4())


class NoOpExternalIdentityLoginSynchronizer(ExternalIdentityLoginSynchronizer):
    async def synchronize(self, *, identity: ExternalIdentity) -> None:
        assert identity.issuer.value
        assert identity.subject.value


class FakeCredentialRepository(CredentialRepository):
    def __init__(self) -> None:
        self.credentials_by_identity: dict[tuple[str, str], UserCredential] = {}
        self.refresh_token_hashes: dict[str, UserCredential] = {}
        self.saved_identities: list[tuple[str, str, str, str | None, str | None]] = []
        self.login_records: list[UUID] = []
        self.revoked_hashes: list[str] = []

    async def find_by_external_identity(
        self,
        *,
        identity: ExternalIdentity,
    ) -> UserCredential | None:
        return self.credentials_by_identity.get((identity.issuer.value, identity.subject.value))

    async def create_for_external_identity(
        self,
        *,
        identity: ExternalIdentity,
        user_id: UUID,
        logged_in_at: datetime,
    ) -> UserCredential:
        assert logged_in_at.tzinfo is not None
        credentials = UserCredential.create(
            user_id=user_id,
            credentials_id=uuid4(),
            role="user",
            last_login_at=logged_in_at,
        )
        identity_key = (identity.issuer.value, identity.subject.value)
        self.credentials_by_identity[identity_key] = credentials
        self.saved_identities.append(
            (
                identity.issuer.value,
                identity.subject.value,
                identity.provider.value,
                identity.email,
                identity.name,
            )
        )
        self.login_records.append(credentials.credentials_id)
        return credentials

    async def record_login(
        self,
        *,
        credentials_id: UUID,
        logged_in_at: datetime,
    ) -> UserCredential:
        assert logged_in_at.tzinfo is not None
        for credentials in self.credentials_by_identity.values():
            if credentials.credentials_id == credentials_id:
                self.login_records.append(credentials.credentials_id)
                return credentials
        raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)

    async def save_refresh_token(
        self,
        *,
        credentials_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        assert expires_at.tzinfo is not None
        for credentials in self.credentials_by_identity.values():
            if credentials.credentials_id == credentials_id:
                self.refresh_token_hashes[token_hash] = credentials
                return
        raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)

    async def rotate_refresh_token(
        self,
        *,
        token_hash: str,
        new_token_hash: str,
        expires_at: datetime,
    ) -> UserCredential:
        assert expires_at.tzinfo is not None
        try:
            credentials = self.refresh_token_hashes.pop(token_hash)
        except KeyError as exc:
            raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE) from exc
        self.refresh_token_hashes[new_token_hash] = credentials
        return credentials

    async def revoke_refresh_token(self, *, token_hash: str) -> None:
        self.refresh_token_hashes.pop(token_hash, None)
        self.revoked_hashes.append(token_hash)

    async def exists_active_credential(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> bool:
        return any(
            credentials.user_id == user_id and credentials.credentials_id == credentials_id
            for credentials in self.credentials_by_identity.values()
        )

    async def delete_account_auth_state(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> None:
        self.credentials_by_identity = {
            identity_key: credentials
            for identity_key, credentials in self.credentials_by_identity.items()
            if credentials.user_id != user_id or credentials.credentials_id != credentials_id
        }
        self.refresh_token_hashes = {
            token_hash: credentials
            for token_hash, credentials in self.refresh_token_hashes.items()
            if credentials.user_id != user_id or credentials.credentials_id != credentials_id
        }


def build_access_token_issuer() -> AccessTokenIssuer:
    return JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )


def build_refresh_token_service() -> OpaqueRefreshTokenIssuer:
    return OpaqueRefreshTokenIssuer(
        pepper="test-pepper",
        expires_days=14,
    )


def build_login_use_case(
    *,
    verifier: FakeExternalIdentityVerifier,
    repository: FakeCredentialRepository,
    user_provisioner: FakeUserProvisioner,
) -> LoginUseCase:
    refresh_token_service = build_refresh_token_service()
    return LoginUseCase(
        identity_verifier=verifier,
        login_synchronizer=NoOpExternalIdentityLoginSynchronizer(),
        credential_repository=repository,
        user_provisioner=user_provisioner,
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=refresh_token_service,
    )


def build_refresh_use_case(*, repository: FakeCredentialRepository) -> RefreshTokenUseCase:
    refresh_token_service = build_refresh_token_service()
    return RefreshTokenUseCase(
        credential_repository=repository,
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=refresh_token_service,
        refresh_token_hasher=refresh_token_service,
    )


def build_logout_use_case(*, repository: FakeCredentialRepository) -> LogoutUseCase:
    refresh_token_service = build_refresh_token_service()
    return LogoutUseCase(
        credential_repository=repository,
        refresh_token_hasher=refresh_token_service,
    )
