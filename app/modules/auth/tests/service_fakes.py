from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.modules.auth.application.commands.login.use_case import LoginCommandUseCase
from app.modules.auth.application.commands.logout.use_case import LogoutCommandUseCase
from app.modules.auth.application.commands.refresh.use_case import RefreshTokenCommandUseCase
from app.modules.auth.application.ports.credential_repository import (
    CredentialRepository,
    SessionCredential,
)
from app.modules.auth.application.ports.external_identity_login_synchronizer import (
    ExternalIdentityLoginSynchronizer,
)
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.application.ports.user_provisioner import (
    ProvisionedUser,
    UserProvisioner,
    UserProvisioningRequest,
)
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
    def __init__(self, *, user_id: UUID | None = None) -> None:
        self.provisioned: list[UserProvisioningRequest] = []
        self._user_id = user_id

    async def provision(self, *, request: UserProvisioningRequest) -> ProvisionedUser:
        self.provisioned.append(request)
        return ProvisionedUser(user_id=self._user_id or uuid4())


class NoOpExternalIdentityLoginSynchronizer(ExternalIdentityLoginSynchronizer):
    async def synchronize(self, *, identity: ExternalIdentity) -> None:
        assert identity.issuer.value
        assert identity.subject.value


class FakeCredentialRepository(CredentialRepository):
    def __init__(self) -> None:
        self.credentials_by_identity: dict[tuple[str, str], UserCredential] = {}
        self.credentials_by_verified_email: dict[str, UserCredential] = {}
        self.credentials_by_user_id: dict[UUID, UserCredential] = {}
        self.refresh_token_hashes: dict[str, SessionCredential] = {}
        self.saved_identities: list[tuple[str, str, str, str | None, str | None]] = []
        self.login_records: list[UUID] = []
        self.revoked_hashes: list[str] = []
        self.revoked_session_ids: set[UUID] = set()

    async def find_by_external_identity(
        self,
        *,
        identity: ExternalIdentity,
    ) -> UserCredential | None:
        return self.credentials_by_identity.get((identity.issuer.value, identity.subject.value))

    async def find_by_verified_email(self, *, canonical_email: str) -> UserCredential | None:
        return self.credentials_by_verified_email.get(canonical_email)

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
        canonical_email = _canonical_email(identity)
        if identity.email_verified and canonical_email is not None:
            self.credentials_by_verified_email[canonical_email] = credentials
        self.credentials_by_identity[identity_key] = credentials
        self.credentials_by_user_id[credentials.user_id] = credentials
        self.saved_identities.append(
            (
                identity.issuer.value,
                identity.subject.value,
                identity.provider.value,
                None if identity.email is None else identity.email.value,
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
        raise AuthenticationError()

    async def find_credential_by_user_id(self, *, user_id: UUID) -> UserCredential | None:
        return self.credentials_by_user_id.get(user_id)

    async def attach_external_identity(
        self,
        *,
        credentials_id: UUID,
        identity: ExternalIdentity,
    ) -> None:
        credentials = next(
            (
                stored
                for stored in self.credentials_by_identity.values()
                if stored.credentials_id == credentials_id
            ),
            None,
        )
        if credentials is None:
            raise AuthenticationError()
        identity_key = (identity.issuer.value, identity.subject.value)
        canonical_email = _canonical_email(identity)
        if identity.email_verified and canonical_email is not None:
            self.credentials_by_verified_email[canonical_email] = credentials
        self.credentials_by_identity[identity_key] = credentials
        self.saved_identities.append(
            (
                identity.issuer.value,
                identity.subject.value,
                identity.provider.value,
                None if identity.email is None else identity.email.value,
                identity.name,
            )
        )

    async def create_session(self, *, credentials_id: UUID) -> UUID:
        assert credentials_id
        return uuid4()

    async def save_refresh_token(
        self,
        *,
        credentials_id: UUID,
        session_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        assert expires_at.tzinfo is not None
        for credentials in self.credentials_by_identity.values():
            if credentials.credentials_id == credentials_id:
                self.refresh_token_hashes[token_hash] = SessionCredential(
                    credentials=credentials,
                    session_id=session_id,
                )
                return
        raise AuthenticationError()

    async def rotate_refresh_token(
        self,
        *,
        token_hash: str,
        new_token_hash: str,
        expires_at: datetime,
    ) -> SessionCredential:
        assert expires_at.tzinfo is not None
        try:
            session_credential = self.refresh_token_hashes.pop(token_hash)
        except KeyError as exc:
            raise AuthenticationError() from exc
        if session_credential.session_id in self.revoked_session_ids:
            raise AuthenticationError()
        self.refresh_token_hashes[new_token_hash] = session_credential
        return session_credential

    async def revoke_session_by_refresh_token(self, *, token_hash: str) -> None:
        session_credential = self.refresh_token_hashes.get(token_hash)
        if session_credential is not None:
            self.revoked_session_ids.add(session_credential.session_id)
            self.refresh_token_hashes = {
                stored_hash: stored_session_credential
                for stored_hash, stored_session_credential in self.refresh_token_hashes.items()
                if stored_session_credential.session_id != session_credential.session_id
            }
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

    async def exists_active_session(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
        session_id: UUID,
    ) -> bool:
        if session_id in self.revoked_session_ids:
            return False
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
        self.credentials_by_user_id = {
            stored_user_id: credentials
            for stored_user_id, credentials in self.credentials_by_user_id.items()
            if credentials.user_id != user_id or credentials.credentials_id != credentials_id
        }
        self.credentials_by_verified_email = {
            email: credentials
            for email, credentials in self.credentials_by_verified_email.items()
            if credentials.user_id != user_id or credentials.credentials_id != credentials_id
        }
        self.refresh_token_hashes = {
            token_hash: session_credential
            for token_hash, session_credential in self.refresh_token_hashes.items()
            if session_credential.credentials.user_id != user_id
            or session_credential.credentials.credentials_id != credentials_id
        }


def build_access_token_issuer() -> JwtAccessTokenService:
    return JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )


def _canonical_email(identity: ExternalIdentity) -> str | None:
    if identity.email is None:
        return None
    return identity.email.value.lower()


def build_refresh_token_service() -> OpaqueRefreshTokenIssuer:
    return OpaqueRefreshTokenIssuer(
        pepper="test-pepper",
        expires_days=14,
    )


def build_login_command_use_case(
    *,
    verifier: FakeExternalIdentityVerifier,
    repository: FakeCredentialRepository,
    user_provisioner: UserProvisioner,
) -> LoginCommandUseCase:
    refresh_token_service = build_refresh_token_service()
    return LoginCommandUseCase(
        identity_verifier=verifier,
        login_synchronizer=NoOpExternalIdentityLoginSynchronizer(),
        credential_repository=repository,
        user_provisioner=user_provisioner,
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=refresh_token_service,
    )


def build_refresh_command_use_case(
    *,
    repository: FakeCredentialRepository,
) -> RefreshTokenCommandUseCase:
    refresh_token_service = build_refresh_token_service()
    return RefreshTokenCommandUseCase(
        credential_repository=repository,
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=refresh_token_service,
        refresh_token_hasher=refresh_token_service,
    )


def build_logout_command_use_case(*, repository: FakeCredentialRepository) -> LogoutCommandUseCase:
    refresh_token_service = build_refresh_token_service()
    return LogoutCommandUseCase(
        credential_repository=repository,
        refresh_token_hasher=refresh_token_service,
    )
