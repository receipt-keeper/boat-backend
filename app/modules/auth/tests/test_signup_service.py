from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.core.domain.exceptions import ValidationError
from app.modules.auth.application.commands.signup.command import SignupCommand
from app.modules.auth.application.commands.signup.use_case import SignupCommandUseCase
from app.modules.auth.application.ports.credit_lifecycle import CreditInitializer
from app.modules.auth.application.ports.external_identity_login_synchronizer import (
    ExternalIdentityLoginSynchronizer,
)
from app.modules.auth.application.ports.notification_settings_initializer import (
    NotificationSettingsInitializer,
)
from app.modules.auth.application.ports.user_provisioner import (
    ProvisionedUser,
    UserProvisioner,
    UserProvisioningRequest,
)
from app.modules.auth.domain.exceptions import UserAlreadyExistsError
from app.modules.auth.domain.model import ExternalIdentity, UserCredential
from app.modules.auth.tests.service_fakes import (
    FakeCredentialRepository,
    FakeExternalIdentityVerifier,
    build_access_token_issuer,
    build_refresh_token_service,
)
from tests.support.unit_of_work import FakeUnitOfWork


@dataclass(frozen=True, slots=True)
class InitializedSettings:
    user_id: UUID
    marketing_consent: bool


@dataclass(frozen=True, slots=True)
class InitializedCredits:
    user_id: UUID


class FakeUserProvisioner(UserProvisioner):
    def __init__(self) -> None:
        self.requests: list[UserProvisioningRequest] = []
        self.user_id = uuid4()

    async def provision(self, *, request: UserProvisioningRequest) -> ProvisionedUser:
        self.requests.append(request)
        return ProvisionedUser(user_id=self.user_id)


class FakeNotificationSettingsInitializer(NotificationSettingsInitializer):
    def __init__(self) -> None:
        self.initialized: list[InitializedSettings] = []

    async def initialize(self, *, user_id: UUID, marketing_consent: bool) -> None:
        self.initialized.append(
            InitializedSettings(
                user_id=user_id,
                marketing_consent=marketing_consent,
            )
        )


class FakeCreditInitializer(CreditInitializer):
    def __init__(self) -> None:
        self.initialized: list[InitializedCredits] = []

    async def initialize(self, *, user_id: UUID) -> None:
        self.initialized.append(InitializedCredits(user_id=user_id))


class RecordingExternalIdentityLoginSynchronizer(ExternalIdentityLoginSynchronizer):
    def __init__(self) -> None:
        self.identities: list[ExternalIdentity] = []

    async def synchronize(self, *, identity: ExternalIdentity) -> None:
        self.identities.append(identity)


@dataclass(frozen=True, slots=True)
class SignupUseCaseFixture:
    use_case: SignupCommandUseCase
    repository: FakeCredentialRepository
    provisioner: FakeUserProvisioner
    notification_initializer: FakeNotificationSettingsInitializer
    credit_initializer: FakeCreditInitializer
    identity_synchronizer: RecordingExternalIdentityLoginSynchronizer
    unit_of_work: FakeUnitOfWork


def _new_identity() -> ExternalIdentity:
    return ExternalIdentity.create(
        issuer="google",
        subject="firebase-uid",
        provider="google",
        email="user@example.com",
        name="테스트 사용자",
        email_verified=True,
    )


def _build_signup_use_case(identity: ExternalIdentity) -> SignupUseCaseFixture:
    repository = FakeCredentialRepository()
    provisioner = FakeUserProvisioner()
    notification_initializer = FakeNotificationSettingsInitializer()
    credit_initializer = FakeCreditInitializer()
    identity_synchronizer = RecordingExternalIdentityLoginSynchronizer()
    unit_of_work = FakeUnitOfWork()
    refresh_token_service = build_refresh_token_service()
    return SignupUseCaseFixture(
        use_case=SignupCommandUseCase(
            identity_verifier=FakeExternalIdentityVerifier(identity),
            identity_synchronizer=identity_synchronizer,
            credential_repository=repository,
            user_provisioner=provisioner,
            notification_settings_initializer=notification_initializer,
            credit_initializer=credit_initializer,
            access_token_issuer=build_access_token_issuer(),
            refresh_token_issuer=refresh_token_service,
            unit_of_work=unit_of_work,
        ),
        repository=repository,
        provisioner=provisioner,
        notification_initializer=notification_initializer,
        credit_initializer=credit_initializer,
        identity_synchronizer=identity_synchronizer,
        unit_of_work=unit_of_work,
    )


def _signup_command(
    *,
    terms_accepted: bool = True,
    privacy_accepted: bool = True,
    terms_version: str | None = "2026-06-01",
    privacy_version: str | None = "2026-06-01",
    marketing_consent: bool = False,
) -> SignupCommand:
    return SignupCommand(
        provider_token="firebase-id-token",
        terms_accepted=terms_accepted,
        privacy_accepted=privacy_accepted,
        terms_version=terms_version,
        privacy_version=privacy_version,
        marketing_consent=marketing_consent,
    )


async def test_signup_creates_new_credentials_tokens_and_marketing_settings() -> None:
    identity = _new_identity()
    fixture = _build_signup_use_case(identity)

    tokens = await fixture.use_case.execute(_signup_command(marketing_consent=True))

    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.expires_in == 1800
    assert fixture.provisioner.requests == [
        UserProvisioningRequest(
            name="테스트 사용자",
            email="user@example.com",
            profile_image_url=None,
            terms_version="2026-06-01",
            privacy_version="2026-06-01",
            terms_accepted=True,
            privacy_accepted=True,
        )
    ]
    assert fixture.notification_initializer.initialized == [
        InitializedSettings(user_id=fixture.provisioner.user_id, marketing_consent=True)
    ]
    assert fixture.credit_initializer.initialized == [
        InitializedCredits(user_id=fixture.provisioner.user_id)
    ]
    assert fixture.identity_synchronizer.identities == [identity]
    assert len(fixture.repository.credentials_by_identity) == 1
    assert len(fixture.repository.refresh_token_hashes) == 1
    assert fixture.unit_of_work.commit_count == 1


async def test_signup_defaults_marketing_settings_to_false() -> None:
    fixture = _build_signup_use_case(_new_identity())

    await fixture.use_case.execute(_signup_command())

    assert fixture.notification_initializer.initialized == [
        InitializedSettings(user_id=fixture.provisioner.user_id, marketing_consent=False)
    ]
    assert fixture.credit_initializer.initialized == [
        InitializedCredits(user_id=fixture.provisioner.user_id)
    ]


async def test_signup_rejects_missing_required_consent_before_provisioning() -> None:
    fixture = _build_signup_use_case(_new_identity())

    with pytest.raises(ValidationError) as error:
        await fixture.use_case.execute(
            _signup_command(
                terms_accepted=False,
                privacy_accepted=False,
            )
        )

    assert [(detail.field, detail.message) for detail in error.value.details] == [
        ("termsAccepted", "이용약관에 동의해야 가입할 수 있습니다."),
        ("privacyAccepted", "개인정보 처리방침에 동의해야 가입할 수 있습니다."),
    ]
    assert fixture.provisioner.requests == []
    assert fixture.notification_initializer.initialized == []
    assert fixture.credit_initializer.initialized == []
    assert fixture.identity_synchronizer.identities == []
    assert fixture.repository.refresh_token_hashes == {}
    assert fixture.unit_of_work.commit_count == 0


async def test_signup_rejects_missing_required_consent_versions_before_provisioning() -> None:
    fixture = _build_signup_use_case(_new_identity())

    with pytest.raises(ValidationError) as error:
        await fixture.use_case.execute(
            _signup_command(
                terms_version=None,
                privacy_version=None,
            )
        )

    assert [(detail.field, detail.message) for detail in error.value.details] == [
        ("termsVersion", "동의한 이용약관 버전이 필요합니다."),
        ("privacyVersion", "동의한 개인정보 처리방침 버전이 필요합니다."),
    ]
    assert fixture.provisioner.requests == []
    assert fixture.notification_initializer.initialized == []
    assert fixture.credit_initializer.initialized == []
    assert fixture.repository.refresh_token_hashes == {}
    assert fixture.unit_of_work.commit_count == 0


async def test_signup_rejects_blank_required_consent_versions_before_provisioning() -> None:
    fixture = _build_signup_use_case(_new_identity())

    with pytest.raises(ValidationError) as error:
        await fixture.use_case.execute(
            _signup_command(
                terms_version="   ",
                privacy_version="",
            )
        )

    assert [(detail.field, detail.message) for detail in error.value.details] == [
        ("termsVersion", "동의한 이용약관 버전이 필요합니다."),
        ("privacyVersion", "동의한 개인정보 처리방침 버전이 필요합니다."),
    ]
    assert fixture.provisioner.requests == []
    assert fixture.notification_initializer.initialized == []
    assert fixture.credit_initializer.initialized == []
    assert fixture.repository.refresh_token_hashes == {}
    assert fixture.unit_of_work.commit_count == 0


async def test_signup_rejects_overlong_consent_versions_before_provisioning() -> None:
    fixture = _build_signup_use_case(_new_identity())

    with pytest.raises(ValidationError) as error:
        await fixture.use_case.execute(
            _signup_command(
                terms_version="v" * 51,
                privacy_version="v" * 51,
            )
        )

    assert [(detail.field, detail.message) for detail in error.value.details] == [
        ("termsVersion", "동의한 이용약관 버전은 50자 이하여야 합니다."),
        ("privacyVersion", "동의한 개인정보 처리방침 버전은 50자 이하여야 합니다."),
    ]
    assert fixture.provisioner.requests == []
    assert fixture.notification_initializer.initialized == []
    assert fixture.repository.refresh_token_hashes == {}
    assert fixture.unit_of_work.commit_count == 0


async def test_signup_rejects_existing_external_identity_without_side_effects() -> None:
    identity = _new_identity()
    fixture = _build_signup_use_case(identity)
    fixture.repository.seed_existing_external_identity(identity=identity)

    with pytest.raises(UserAlreadyExistsError) as error:
        await fixture.use_case.execute(_signup_command(marketing_consent=True))

    assert error.value.code == "USER_ALREADY_EXISTS"
    assert fixture.provisioner.requests == []
    assert fixture.notification_initializer.initialized == []
    assert fixture.credit_initializer.initialized == []
    assert fixture.identity_synchronizer.identities == []
    assert fixture.repository.refresh_token_hashes == {}
    assert fixture.unit_of_work.commit_count == 0


async def test_signup_rejects_verified_email_existing_credential_without_attach_or_login() -> None:
    identity = _new_identity()
    fixture = _build_signup_use_case(identity)
    fixture.repository.credentials_by_verified_email["user@example.com"] = UserCredential.create(
        user_id=uuid4(),
        credentials_id=uuid4(),
        role="user",
    )

    with pytest.raises(UserAlreadyExistsError):
        await fixture.use_case.execute(_signup_command())

    assert fixture.repository.credentials_by_identity == {}
    assert fixture.repository.saved_identities == []
    assert fixture.repository.login_records == []
    assert fixture.repository.refresh_token_hashes == {}
    assert fixture.provisioner.requests == []
    assert fixture.notification_initializer.initialized == []
    assert fixture.credit_initializer.initialized == []
    assert fixture.identity_synchronizer.identities == []
