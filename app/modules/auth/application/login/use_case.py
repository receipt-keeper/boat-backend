from datetime import UTC, datetime

from app.modules.auth.application.constants import AUTH_SCHEME_BEARER
from app.modules.auth.application.login.schemas import LoginCommand, LoginResult
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.external_identity_login_synchronizer import (
    ExternalIdentityLoginSynchronizer,
)
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.application.ports.token_issuer import AccessTokenIssuer, RefreshTokenIssuer
from app.modules.auth.application.ports.user_provisioner import UserProvisioner


class LoginUseCase:
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
        if credentials is None:
            provisioned_user = await self._user_provisioner.provision(
                name=identity.name,
                email=identity.email,
            )
            credentials = await self._credential_repository.create_for_external_identity(
                identity=identity,
                user_id=provisioned_user.user_id,
                logged_in_at=logged_in_at,
            )
        else:
            credentials = await self._credential_repository.record_login(
                credentials_id=credentials.credentials_id,
                logged_in_at=logged_in_at,
            )

        refresh_token = self._refresh_token_issuer.issue()
        await self._credential_repository.save_refresh_token(
            credentials_id=credentials.credentials_id,
            token_hash=refresh_token.token_hash,
            expires_at=refresh_token.expires_at,
        )
        access_token = self._access_token_issuer.issue(
            user_id=credentials.user_id,
            credentials_id=credentials.credentials_id,
            role=credentials.role.value,
        )

        return LoginResult(
            access_token=access_token.token,
            refresh_token=refresh_token.token,
            token_type=AUTH_SCHEME_BEARER,
            expires_in=access_token.expires_in,
        )
