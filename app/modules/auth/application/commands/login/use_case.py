from datetime import UTC, datetime

from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.application.commands.login.result import LoginResult
from app.modules.auth.application.constants import AUTH_SCHEME_BEARER, AUTHENTICATION_FAILED_MESSAGE
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.external_identity_login_synchronizer import (
    ExternalIdentityLoginSynchronizer,
)
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.application.ports.token_issuer import AccessTokenIssuer, RefreshTokenIssuer
from app.modules.auth.application.ports.user_provisioner import (
    UserProvisioner,
    UserProvisioningRequest,
)
from app.modules.auth.domain.exceptions import AuthenticationError


class LoginCommandUseCase:
    def __init__(
        self,
        *,
        identity_verifier: ExternalIdentityVerifier,
        login_synchronizer: ExternalIdentityLoginSynchronizer,
        credential_repository: CredentialRepository,
        user_provisioner: UserProvisioner,
        access_token_issuer: AccessTokenIssuer,
        refresh_token_issuer: RefreshTokenIssuer,
    ) -> None:
        self._identity_verifier = identity_verifier
        self._login_synchronizer = login_synchronizer
        self._credential_repository = credential_repository
        self._user_provisioner = user_provisioner
        self._access_token_issuer = access_token_issuer
        self._refresh_token_issuer = refresh_token_issuer

    async def execute(self, command: LoginCommand) -> LoginResult:
        identity = await self._identity_verifier.verify(command.provider_token)
        await self._login_synchronizer.synchronize(identity=identity)
        logged_in_at = datetime.now(UTC)
        credentials = await self._credential_repository.find_by_external_identity(
            identity=identity,
        )
        if credentials is not None:
            credentials = await self._credential_repository.record_login(
                credentials_id=credentials.credentials_id,
                logged_in_at=logged_in_at,
            )
        else:
            if not identity.email_verified or identity.normalized_email is None:
                raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)
            provisioned = await self._user_provisioner.provision(
                request=UserProvisioningRequest(
                    name=identity.name,
                    email=identity.email,
                    normalized_email=identity.normalized_email.value,
                    profile_image_url=None,
                    terms_version=command.terms_version,
                    privacy_version=command.privacy_version,
                    terms_accepted=command.terms_accepted,
                    privacy_accepted=command.privacy_accepted,
                    marketing_consent=command.marketing_consent,
                )
            )
            existing = await self._credential_repository.find_credential_by_user_id(
                user_id=provisioned.user_id,
            )
            if existing is not None:
                await self._credential_repository.attach_external_identity(
                    credentials_id=existing.credentials_id,
                    identity=identity,
                )
                credentials = await self._credential_repository.record_login(
                    credentials_id=existing.credentials_id,
                    logged_in_at=logged_in_at,
                )
            else:
                credentials = await self._credential_repository.create_for_external_identity(
                    identity=identity,
                    user_id=provisioned.user_id,
                    logged_in_at=logged_in_at,
                )

        session_id = await self._credential_repository.create_session(
            credentials_id=credentials.credentials_id,
        )
        refresh_token = self._refresh_token_issuer.issue()
        await self._credential_repository.save_refresh_token(
            credentials_id=credentials.credentials_id,
            session_id=session_id,
            token_hash=refresh_token.token_hash,
            expires_at=refresh_token.expires_at,
        )
        access_token = self._access_token_issuer.issue(
            user_id=credentials.user_id,
            credentials_id=credentials.credentials_id,
            session_id=session_id,
            role=credentials.role.value,
        )

        return LoginResult(
            access_token=access_token.token,
            refresh_token=refresh_token.token,
            token_type=AUTH_SCHEME_BEARER,
            expires_in=access_token.expires_in,
        )
