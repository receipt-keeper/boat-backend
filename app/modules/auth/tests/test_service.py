from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
import pytest

from app.modules.auth.application.constants import AUTH_SCHEME_BEARER, AUTHENTICATION_FAILED_MESSAGE
from app.modules.auth.application.login.schemas import LoginCommand
from app.modules.auth.application.logout.schemas import LogoutCommand
from app.modules.auth.application.refresh.schemas import RefreshTokenCommand
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity, UserCredential
from app.modules.auth.infrastructure.tokens.jwt import (
    JWT_CLAIM_CREDENTIALS_ID,
    JWT_CLAIM_ROLE,
    JWT_CLAIM_SUBJECT,
    JwtAccessTokenService,
)
from app.modules.auth.tests.service_fakes import (
    TEST_SIGNING_KEY,
    FakeCredentialRepository,
    FakeExternalIdentityVerifier,
    FakeUserProvisioner,
    build_login_use_case,
    build_logout_use_case,
    build_refresh_use_case,
)


async def test_login_creates_credentials_and_returns_service_tokens() -> None:
    repository = FakeCredentialRepository()
    user_provisioner = FakeUserProvisioner()
    use_case = build_login_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="firebase",
                subject="firebase-uid",
                provider="apple.com",
                email="user@example.com",
                name="테스트 사용자",
            )
        ),
        repository=repository,
        user_provisioner=user_provisioner,
    )

    tokens = await use_case.execute(LoginCommand(provider_token="firebase-id-token"))

    assert tokens.token_type == AUTH_SCHEME_BEARER
    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.expires_in == 1800
    assert user_provisioner.provisioned == [("테스트 사용자", "user@example.com")]
    assert repository.saved_identities == [
        ("firebase", "firebase-uid", "apple.com", "user@example.com", "테스트 사용자")
    ]
    assert repository.login_records == [
        repository.credentials_by_identity[("firebase", "firebase-uid")].credentials_id
    ]


async def test_login_uses_existing_external_identity_without_duplicate_credentials() -> None:
    repository = FakeCredentialRepository()
    user_provisioner = FakeUserProvisioner()
    existing_credentials = UserCredential.create(
        user_id=uuid4(),
        credentials_id=uuid4(),
        role="user",
    )
    repository.credentials_by_identity[("firebase", "firebase-uid")] = existing_credentials
    use_case = build_login_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="firebase",
                subject="firebase-uid",
                provider="apple.com",
                email="user@example.com",
                name=None,
            )
        ),
        repository=repository,
        user_provisioner=user_provisioner,
    )

    await use_case.execute(LoginCommand(provider_token="firebase-id-token"))

    assert repository.credentials_by_identity[("firebase", "firebase-uid")] == existing_credentials
    assert len(repository.credentials_by_identity) == 1
    assert repository.saved_identities == []
    assert user_provisioner.provisioned == []
    assert repository.login_records == [existing_credentials.credentials_id]


async def test_login_does_not_store_refresh_token_when_identity_verification_fails() -> None:
    repository = FakeCredentialRepository()
    use_case = build_login_use_case(
        verifier=FakeExternalIdentityVerifier(
            error=AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)
        ),
        repository=repository,
        user_provisioner=FakeUserProvisioner(),
    )

    with pytest.raises(AuthenticationError):
        await use_case.execute(LoginCommand(provider_token="bad-token"))

    assert repository.credentials_by_identity == {}
    assert repository.refresh_token_hashes == {}


async def test_refresh_rotates_refresh_token_and_rejects_old_token() -> None:
    repository = FakeCredentialRepository()
    login_use_case = build_login_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="firebase",
                subject="firebase-uid",
                provider="apple.com",
                email=None,
                name=None,
            )
        ),
        repository=repository,
        user_provisioner=FakeUserProvisioner(),
    )
    refresh_use_case = build_refresh_use_case(repository=repository)
    first_pair = await login_use_case.execute(LoginCommand(provider_token="firebase-id-token"))
    old_hashes = set(repository.refresh_token_hashes)

    second_pair = await refresh_use_case.execute(
        RefreshTokenCommand(refresh_token=first_pair.refresh_token)
    )

    assert second_pair.refresh_token != first_pair.refresh_token
    assert old_hashes.isdisjoint(repository.refresh_token_hashes)
    with pytest.raises(AuthenticationError):
        await refresh_use_case.execute(RefreshTokenCommand(refresh_token=first_pair.refresh_token))


async def test_logout_revokes_only_presented_refresh_token() -> None:
    repository = FakeCredentialRepository()
    login_use_case = build_login_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="firebase",
                subject="firebase-uid",
                provider="apple.com",
                email=None,
                name=None,
            )
        ),
        repository=repository,
        user_provisioner=FakeUserProvisioner(),
    )
    logout_use_case = build_logout_use_case(repository=repository)
    tokens = await login_use_case.execute(LoginCommand(provider_token="firebase-id-token"))
    token_hash = next(iter(repository.refresh_token_hashes))

    await logout_use_case.execute(LogoutCommand(refresh_token=tokens.refresh_token))

    assert token_hash not in repository.refresh_token_hashes
    assert repository.revoked_hashes == [token_hash]


def test_access_token_contains_principal_claims() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    credentials_id = UUID("00000000-0000-0000-0000-000000000002")

    issued = manager.issue(user_id=user_id, credentials_id=credentials_id, role="admin")
    principal = manager.verify(issued.token)

    assert principal.user_id == user_id
    assert principal.credentials_id == credentials_id
    assert principal.role == "admin"
    assert issued.expires_at > datetime.now(UTC)


def test_access_token_verify_rejects_malformed_subject_with_authentication_error() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    issued = manager.issue(user_id=uuid4(), credentials_id=uuid4(), role="user")
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    claims[JWT_CLAIM_SUBJECT] = "not-a-uuid"
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == AUTHENTICATION_FAILED_MESSAGE


def test_access_token_verify_rejects_malformed_credentials_id_with_authentication_error() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    issued = manager.issue(user_id=uuid4(), credentials_id=uuid4(), role="user")
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    claims[JWT_CLAIM_CREDENTIALS_ID] = "not-a-uuid"
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == AUTHENTICATION_FAILED_MESSAGE


def test_access_token_verify_rejects_missing_required_claims_with_authentication_error() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    issued = manager.issue(user_id=uuid4(), credentials_id=uuid4(), role="user")
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    del claims[JWT_CLAIM_ROLE]
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == AUTHENTICATION_FAILED_MESSAGE
