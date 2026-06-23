from datetime import UTC, datetime

from app.core.application.unit_of_work import UnitOfWork
from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.application.commands.login.result import LoginResult
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
from app.modules.auth.domain.model import ExternalIdentity


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
        unit_of_work: UnitOfWork,
    ) -> None:
        self._identity_verifier = identity_verifier
        self._login_synchronizer = login_synchronizer
        self._credential_repository = credential_repository
        self._user_provisioner = user_provisioner
        self._access_token_issuer = access_token_issuer
        self._refresh_token_issuer = refresh_token_issuer
        self._unit_of_work = unit_of_work

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
            canonical_email = _canonical_email(identity)
            if not identity.email_verified or canonical_email is None:
                raise AuthenticationError()
            credentials = await self._credential_repository.find_by_verified_email(
                canonical_email=canonical_email
            )
            if credentials is not None:
                await self._credential_repository.attach_external_identity(
                    credentials_id=credentials.credentials_id,
                    identity=identity,
                )
                credentials = await self._credential_repository.record_login(
                    credentials_id=credentials.credentials_id,
                    logged_in_at=logged_in_at,
                )
            else:
                provisioned = await self._user_provisioner.provision(
                    request=UserProvisioningRequest(
                        name=identity.name,
                        email=None if identity.email is None else identity.email.value,
                        profile_image_url=None,
                        terms_version=command.terms_version,
                        privacy_version=command.privacy_version,
                        terms_accepted=command.terms_accepted,
                        privacy_accepted=command.privacy_accepted,
                        marketing_consent=command.marketing_consent,
                    )
                )
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
        await self._unit_of_work.commit()

        return LoginResult(
            access_token=access_token.token,
            refresh_token=refresh_token.token,
            expires_in=access_token.expires_in,
        )


def _canonical_email(identity: ExternalIdentity) -> str | None:
    if identity.email is None:
        return None
    return identity.email.value.lower()
