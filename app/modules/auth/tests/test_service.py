from uuid import uuid4

import pytest

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.application.ports.user_provisioner import (
    ProvisionedUser,
    UserProvisioner,
    UserProvisioningRequest,
)
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity, UserCredential
from app.modules.auth.tests.service_fakes import (
    FakeCredentialRepository,
    FakeExternalIdentityVerifier,
    FakeUserProvisioner,
    build_login_command_use_case,
)


class _ConsentEnforcingUserProvisioner(UserProvisioner):
    async def provision(self, *, request: UserProvisioningRequest) -> ProvisionedUser:
        details: list[ErrorDetail] = []
        if not request.terms_accepted:
            details.append(
                ErrorDetail(field="termsAccepted", message="이용약관 동의가 필요합니다.")
            )
        if not request.privacy_accepted:
            details.append(
                ErrorDetail(field="privacyAccepted", message="개인정보 동의가 필요합니다.")
            )
        if details:
            raise ValidationError(details)
        return ProvisionedUser(user_id=uuid4())


async def test_login_creates_credentials_and_returns_service_tokens() -> None:
    repository = FakeCredentialRepository()
    user_provisioner = FakeUserProvisioner()
    command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="apple",
                subject="firebase-uid",
                provider="apple",
                email="user@example.com",
                name="테스트 사용자",
                email_verified=True,
            )
        ),
        repository=repository,
        user_provisioner=user_provisioner,
    )

    tokens = await command_use_case.execute(
        LoginCommand(
            provider_token="firebase-id-token",
            terms_accepted=True,
            privacy_accepted=True,
        )
    )

    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.expires_in == 1800
    assert len(user_provisioner.provisioned) == 1
    provisioning_request = user_provisioner.provisioned[0]
    assert provisioning_request.name == "테스트 사용자"
    assert provisioning_request.email == "user@example.com"
    assert not hasattr(provisioning_request, "normalized_email")
    assert provisioning_request.terms_accepted is True
    assert provisioning_request.privacy_accepted is True
    assert repository.saved_identities == [
        ("apple", "firebase-uid", "apple", "user@example.com", "테스트 사용자")
    ]
    assert repository.login_records == [
        repository.credentials_by_identity[("apple", "firebase-uid")].credentials_id
    ]


async def test_login_rejects_new_signup_without_consent() -> None:
    repository = FakeCredentialRepository()
    command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="google",
                subject="firebase-uid",
                provider="google",
                email="user@example.com",
                name="테스트 사용자",
                email_verified=True,
            )
        ),
        repository=repository,
        user_provisioner=_ConsentEnforcingUserProvisioner(),
    )

    with pytest.raises(ValidationError) as error:
        await command_use_case.execute(
            LoginCommand(provider_token="firebase-id-token", terms_accepted=False)
        )

    assert {detail.field for detail in error.value.details} == {
        "termsAccepted",
        "privacyAccepted",
    }
    assert repository.credentials_by_identity == {}
    assert repository.refresh_token_hashes == {}


async def test_login_rejects_new_external_identity_without_verified_email() -> None:
    repository = FakeCredentialRepository()
    user_provisioner = FakeUserProvisioner()
    command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="google",
                subject="firebase-uid",
                provider="google",
                email="user@example.com",
                name="테스트 사용자",
                email_verified=False,
            )
        ),
        repository=repository,
        user_provisioner=user_provisioner,
    )

    with pytest.raises(AuthenticationError):
        await command_use_case.execute(
            LoginCommand(
                provider_token="firebase-id-token",
                terms_accepted=True,
                privacy_accepted=True,
            )
        )

    assert user_provisioner.provisioned == []
    assert repository.credentials_by_identity == {}
    assert repository.refresh_token_hashes == {}


async def test_login_uses_existing_external_identity_without_duplicate_credentials() -> None:
    repository = FakeCredentialRepository()
    user_provisioner = FakeUserProvisioner()
    existing_credentials = UserCredential.create(
        user_id=uuid4(),
        credentials_id=uuid4(),
        role="user",
    )
    repository.credentials_by_identity[("apple", "firebase-uid")] = existing_credentials
    command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="apple",
                subject="firebase-uid",
                provider="apple",
                email="user@example.com",
                name=None,
            )
        ),
        repository=repository,
        user_provisioner=user_provisioner,
    )

    await command_use_case.execute(LoginCommand(provider_token="firebase-id-token"))

    assert repository.credentials_by_identity[("apple", "firebase-uid")] == existing_credentials
    assert len(repository.credentials_by_identity) == 1
    assert repository.saved_identities == []
    assert user_provisioner.provisioned == []
    assert repository.login_records == [existing_credentials.credentials_id]


async def test_login_does_not_store_refresh_token_when_identity_verification_fails() -> None:
    repository = FakeCredentialRepository()
    command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(error=AuthenticationError()),
        repository=repository,
        user_provisioner=FakeUserProvisioner(),
    )

    with pytest.raises(AuthenticationError):
        await command_use_case.execute(LoginCommand(provider_token="bad-token"))

    assert repository.credentials_by_identity == {}
    assert repository.refresh_token_hashes == {}
