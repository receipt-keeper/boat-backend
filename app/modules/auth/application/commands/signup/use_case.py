from datetime import UTC, datetime
from typing import Final

from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.auth.application.commands.signup.command import SignupCommand
from app.modules.auth.application.commands.signup.result import SignupResult
from app.modules.auth.application.ports.benefit_subject_handle import (
    BenefitSubjectHandleProvider,
)
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.credit_lifecycle import CreditInitializer
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

MAX_CONSENT_VERSION_LENGTH: Final = 50


class SignupCommandUseCase:
    def __init__(
        self,
        *,
        identity_verifier: ExternalIdentityVerifier,
        identity_synchronizer: ExternalIdentityLoginSynchronizer,
        credential_repository: CredentialRepository,
        user_provisioner: UserProvisioner,
        notification_settings_initializer: NotificationSettingsInitializer,
        credit_initializer: CreditInitializer,
        benefit_subject_handle_provider: BenefitSubjectHandleProvider,
        access_token_issuer: AccessTokenIssuer,
        refresh_token_issuer: RefreshTokenIssuer,
        unit_of_work: UnitOfWork,
        event_publisher: EventPublisher,
    ) -> None:
        self._identity_verifier = identity_verifier
        self._identity_synchronizer = identity_synchronizer
        self._credential_repository = credential_repository
        self._user_provisioner = user_provisioner
        self._notification_settings_initializer = notification_settings_initializer
        self._credit_initializer = credit_initializer
        self._benefit_subject_handle_provider = benefit_subject_handle_provider
        self._access_token_issuer = access_token_issuer
        self._refresh_token_issuer = refresh_token_issuer
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher

    async def execute(self, command: SignupCommand) -> SignupResult:
        terms_version = _normalized_consent_version(command.terms_version)
        privacy_version = _normalized_consent_version(command.privacy_version)
        details: list[ErrorDetail] = []
        if not command.terms_accepted:
            details.append(
                ErrorDetail(
                    field="termsAccepted", message="이용약관에 동의해야 가입할 수 있습니다."
                )
            )
        if command.terms_accepted and terms_version is None:
            details.append(
                ErrorDetail(field="termsVersion", message="동의한 이용약관 버전이 필요합니다.")
            )
        if (
            command.terms_accepted
            and terms_version is not None
            and len(terms_version) > MAX_CONSENT_VERSION_LENGTH
        ):
            details.append(
                ErrorDetail(
                    field="termsVersion",
                    message="동의한 이용약관 버전은 50자 이하여야 합니다.",
                )
            )
        if not command.privacy_accepted:
            details.append(
                ErrorDetail(
                    field="privacyAccepted",
                    message="개인정보 처리방침에 동의해야 가입할 수 있습니다.",
                )
            )
        if command.privacy_accepted and privacy_version is None:
            details.append(
                ErrorDetail(
                    field="privacyVersion", message="동의한 개인정보 처리방침 버전이 필요합니다."
                )
            )
        if (
            command.privacy_accepted
            and privacy_version is not None
            and len(privacy_version) > MAX_CONSENT_VERSION_LENGTH
        ):
            details.append(
                ErrorDetail(
                    field="privacyVersion",
                    message="동의한 개인정보 처리방침 버전은 50자 이하여야 합니다.",
                )
            )
        if details:
            raise ValidationError(details)

        identity = await self._identity_verifier.verify(command.provider_token)
        await self._ensure_new_user(identity)
        await self._identity_synchronizer.synchronize(identity=identity)

        provisioned_user = await self._user_provisioner.provision(
            request=UserProvisioningRequest(
                name=identity.name,
                email=None if identity.email is None else identity.email.value,
                profile_image_url=None,
                terms_version=terms_version,
                privacy_version=privacy_version,
                terms_accepted=command.terms_accepted,
                privacy_accepted=command.privacy_accepted,
            )
        )
        await self._notification_settings_initializer.initialize(
            user_id=provisioned_user.user_id,
            marketing_consent=command.marketing_consent,
        )
        subject_handle = self._benefit_subject_handle_provider.handle(
            subject=identity.subject.value,
        )
        candidate_handles = self._benefit_subject_handle_provider.candidate_handles(
            subject=identity.subject.value,
        )
        # 재가입 신원 판정은 credits(claim 원장)가 소유한다 - auth는 항상 무조건
        # 발급 포트를 호출하고, 재지급 여부는 credits의 claim-first 로직이 결정한다.
        await self._credit_initializer.initialize(
            user_id=provisioned_user.user_id,
            subject_handle=subject_handle,
            candidate_handles=candidate_handles,
        )
        logged_in_at = datetime.now(UTC)
        credentials = await self._credential_repository.create_for_external_identity(
            identity=identity,
            user_id=provisioned_user.user_id,
            logged_in_at=logged_in_at,
        )
        await self._event_publisher.publish(credentials.pull_events())
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


def _normalized_consent_version(version: str | None) -> str | None:
    if version is None:
        return None

    normalized = version.strip()
    if normalized == "":
        return None
    return normalized
