from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
import pytest

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.application.commands.logout.command import LogoutCommand
from app.modules.auth.application.commands.refresh.command import RefreshTokenCommand
from app.modules.auth.application.ports.credential_repository import CredentialRepositoryProvider
from app.modules.auth.application.ports.user_provisioner import (
    ProvisionedUser,
    UserProvisioner,
    UserProvisioningRequest,
)
from app.modules.auth.application.queries.current_principal.query import CurrentPrincipalQuery
from app.modules.auth.application.queries.current_principal.use_case import (
    CurrentPrincipalQueryUseCase,
)
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity, UserCredential
from app.modules.auth.infrastructure.tokens.jwt import (
    JWT_CLAIM_CREDENTIALS_ID,
    JWT_CLAIM_ROLE,
    JWT_CLAIM_SESSION_ID,
    JWT_CLAIM_SUBJECT,
    JwtAccessTokenService,
)
from app.modules.auth.tests.service_fakes import (
    TEST_SIGNING_KEY,
    FakeCredentialRepository,
    FakeExternalIdentityVerifier,
    FakeUserProvisioner,
    build_access_token_issuer,
    build_login_command_use_case,
    build_logout_command_use_case,
    build_refresh_command_use_case,
)


class StaticCredentialRepositoryProvider(CredentialRepositoryProvider):
    def __init__(self, repository: FakeCredentialRepository) -> None:
        self._repository = repository

    def get(self) -> FakeCredentialRepository:
        return self._repository


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
                normalized_email="user@example.com",
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
    assert provisioning_request.normalized_email == "user@example.com"
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
                normalized_email="user@example.com",
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
                normalized_email="user@example.com",
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


async def test_refresh_rotates_refresh_token_and_rejects_old_token() -> None:
    repository = FakeCredentialRepository()
    login_command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="apple",
                subject="firebase-uid",
                provider="apple",
                email="user@example.com",
                name=None,
                normalized_email="user@example.com",
                email_verified=True,
            )
        ),
        repository=repository,
        user_provisioner=FakeUserProvisioner(),
    )
    refresh_command_use_case = build_refresh_command_use_case(repository=repository)
    first_pair = await login_command_use_case.execute(
        LoginCommand(
            provider_token="firebase-id-token",
            terms_accepted=True,
            privacy_accepted=True,
        )
    )
    old_hashes = set(repository.refresh_token_hashes)

    second_pair = await refresh_command_use_case.execute(
        RefreshTokenCommand(refresh_token=first_pair.refresh_token)
    )

    assert second_pair.refresh_token != first_pair.refresh_token
    assert old_hashes.isdisjoint(repository.refresh_token_hashes)
    with pytest.raises(AuthenticationError):
        await refresh_command_use_case.execute(
            RefreshTokenCommand(refresh_token=first_pair.refresh_token)
        )


async def test_logout_revokes_only_presented_refresh_token() -> None:
    repository = FakeCredentialRepository()
    login_command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="apple",
                subject="firebase-uid",
                provider="apple",
                email="user@example.com",
                name=None,
                normalized_email="user@example.com",
                email_verified=True,
            )
        ),
        repository=repository,
        user_provisioner=FakeUserProvisioner(),
    )
    logout_command_use_case = build_logout_command_use_case(repository=repository)
    tokens = await login_command_use_case.execute(
        LoginCommand(
            provider_token="firebase-id-token",
            terms_accepted=True,
            privacy_accepted=True,
        )
    )
    token_hash = next(iter(repository.refresh_token_hashes))

    await logout_command_use_case.execute(LogoutCommand(refresh_token=tokens.refresh_token))

    assert token_hash not in repository.refresh_token_hashes
    assert repository.revoked_hashes == [token_hash]


async def test_logout_invalidates_same_session_access_token() -> None:
    repository = FakeCredentialRepository()
    login_command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="apple",
                subject="firebase-uid",
                provider="apple",
                email="user@example.com",
                name=None,
                normalized_email="user@example.com",
                email_verified=True,
            )
        ),
        repository=repository,
        user_provisioner=FakeUserProvisioner(),
    )
    current_principal_query_use_case = CurrentPrincipalQueryUseCase(
        access_token_verifier=build_access_token_issuer(),
        credential_repository_provider=StaticCredentialRepositoryProvider(repository),
    )
    logout_command_use_case = build_logout_command_use_case(repository=repository)
    tokens = await login_command_use_case.execute(
        LoginCommand(
            provider_token="firebase-id-token",
            terms_accepted=True,
            privacy_accepted=True,
        )
    )

    principal = await current_principal_query_use_case.execute(
        CurrentPrincipalQuery(token=tokens.access_token)
    )
    await logout_command_use_case.execute(LogoutCommand(refresh_token=tokens.refresh_token))

    assert principal.credentials_id in repository.login_records
    with pytest.raises(AuthenticationError):
        await current_principal_query_use_case.execute(
            CurrentPrincipalQuery(token=tokens.access_token)
        )


def test_access_token_contains_principal_claims() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    credentials_id = UUID("00000000-0000-0000-0000-000000000002")
    session_id = UUID("00000000-0000-0000-0000-000000000003")

    issued = manager.issue(
        user_id=user_id,
        credentials_id=credentials_id,
        session_id=session_id,
        role="admin",
    )
    principal = manager.verify(issued.token)

    assert principal.user_id == user_id
    assert principal.credentials_id == credentials_id
    assert principal.session_id == session_id
    assert principal.role == "admin"
    assert issued.expires_at > datetime.now(UTC)


def test_access_token_verify_rejects_malformed_subject_with_authentication_error() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    issued = manager.issue(
        user_id=uuid4(),
        credentials_id=uuid4(),
        session_id=uuid4(),
        role="user",
    )
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    claims[JWT_CLAIM_SUBJECT] = "not-a-uuid"
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == "인증 정보가 올바르지 않습니다."


def test_access_token_verify_rejects_malformed_credentials_id_with_authentication_error() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    issued = manager.issue(
        user_id=uuid4(),
        credentials_id=uuid4(),
        session_id=uuid4(),
        role="user",
    )
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    claims[JWT_CLAIM_CREDENTIALS_ID] = "not-a-uuid"
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == "인증 정보가 올바르지 않습니다."


def test_access_token_verify_rejects_missing_required_claims_with_authentication_error() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    issued = manager.issue(
        user_id=uuid4(),
        credentials_id=uuid4(),
        session_id=uuid4(),
        role="user",
    )
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    del claims[JWT_CLAIM_ROLE]
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == "인증 정보가 올바르지 않습니다."


def test_access_token_verify_rejects_malformed_session_id_with_authentication_error() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    issued = manager.issue(
        user_id=uuid4(),
        credentials_id=uuid4(),
        session_id=uuid4(),
        role="user",
    )
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    claims[JWT_CLAIM_SESSION_ID] = "not-a-uuid"
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == "인증 정보가 올바르지 않습니다."


def test_access_token_verify_rejects_missing_session_id_with_authentication_error() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    issued = manager.issue(
        user_id=uuid4(),
        credentials_id=uuid4(),
        session_id=uuid4(),
        role="user",
    )
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    del claims[JWT_CLAIM_SESSION_ID]
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == "인증 정보가 올바르지 않습니다."
