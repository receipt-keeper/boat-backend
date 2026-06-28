from datetime import UTC, datetime

from app.core.application.unit_of_work import UnitOfWork
from app.modules.auth.application.commands.signup.command import SignupCommand
from app.modules.auth.application.commands.signup.result import SignupResult
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.external_identity_login_synchronizer import (
    ExternalIdentityLoginSynchronizer,
)
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.application.ports.notification_settings_initializer import (
    NotificationSettingsInitializer,
)
from app.modules.auth.application.ports.token_issuer import AccessTokenIssuer, RefreshTokenIssuer
from app.modules.auth.application.ports.user_provisioner import (
    UserProvisioner,
    UserProvisioningRequest,
)
from app.modules.auth.domain.exceptions import UserAlreadyExistsError
from app.modules.auth.domain.model import ExternalIdentity


class SignupCommandUseCase:
    def __init__(
        self,
        *,
        identity_verifier: ExternalIdentityVerifier,
        identity_synchronizer: ExternalIdentityLoginSynchronizer,
        credential_repository: CredentialRepository,
        user_provisioner: UserProvisioner,
        notification_settings_initializer: NotificationSettingsInitializer,
        access_token_issuer: AccessTokenIssuer,
        refresh_token_issuer: RefreshTokenIssuer,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._identity_verifier = identity_verifier
        self._identity_synchronizer = identity_synchronizer
        self._credential_repository = credential_repository
        self._user_provisioner = user_provisioner
        self._notification_settings_initializer = notification_settings_initializer
        self._access_token_issuer = access_token_issuer
        self._refresh_token_issuer = refresh_token_issuer
        self._unit_of_work = unit_of_work

    async def execute(self, command: SignupCommand) -> SignupResult:
        identity = await self._identity_verifier.verify(command.provider_token)
        await self._identity_synchronizer.synchronize(identity=identity)
        await self._ensure_new_user(identity)

        provisioned_user = await self._user_provisioner.provision(
            request=UserProvisioningRequest(
                name=identity.name,
                email=None if identity.email is None else identity.email.value,
                profile_image_url=None,
                terms_version=command.terms_version,
                privacy_version=command.privacy_version,
                terms_accepted=command.terms_accepted,
                privacy_accepted=command.privacy_accepted,
            )
        )
        await self._notification_settings_initializer.initialize(
            user_id=provisioned_user.user_id,
            marketing_consent=command.marketing_consent,
        )
        logged_in_at = datetime.now(UTC)
        credentials = await self._credential_repository.create_for_external_identity(
            identity=identity,
            user_id=provisioned_user.user_id,
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

        return SignupResult(
            access_token=access_token.token,
            refresh_token=refresh_token.token,
            expires_in=access_token.expires_in,
        )

    async def _ensure_new_user(self, identity: ExternalIdentity) -> None:
        existing_credentials = await self._credential_repository.find_by_external_identity(
            identity=identity,
        )
        if existing_credentials is not None:
            raise UserAlreadyExistsError()

        canonical_email = _canonical_email(identity)
        if identity.email_verified and canonical_email is not None:
            existing_credentials = await self._credential_repository.find_by_verified_email(
                canonical_email=canonical_email,
            )
            if existing_credentials is not None:
                raise UserAlreadyExistsError()


def _canonical_email(identity: ExternalIdentity) -> str | None:
    if identity.email is None:
        return None
    return identity.email.value.lower()
