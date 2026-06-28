from uuid import uuid4

import pytest

from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.domain.exceptions import AuthenticationError, UserNotRegisteredError
from app.modules.auth.domain.model import ExternalIdentity, UserCredential
from app.modules.auth.tests.service_fakes import (
    FakeCredentialRepository,
    FakeExternalIdentityVerifier,
    build_login_command_use_case,
)


async def test_login_rejects_new_identity_without_creating_credentials_or_tokens() -> None:
    repository = FakeCredentialRepository()
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
    )

    with pytest.raises(UserNotRegisteredError) as error:
        await command_use_case.execute(LoginCommand(provider_token="firebase-id-token"))

    assert error.value.code == "USER_NOT_REGISTERED"
    assert repository.credentials_by_identity == {}
    assert repository.credentials_by_verified_email == {}
    assert repository.saved_identities == []
    assert repository.login_records == []
    assert repository.refresh_token_hashes == {}


async def test_login_uses_existing_external_identity_without_duplicate_credentials() -> None:
    repository = FakeCredentialRepository()
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
    )

    tokens = await command_use_case.execute(LoginCommand(provider_token="firebase-id-token"))

    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.expires_in == 1800
    assert repository.credentials_by_identity[("apple", "firebase-uid")] == existing_credentials
    assert len(repository.credentials_by_identity) == 1
    assert repository.saved_identities == []
    assert repository.login_records == [existing_credentials.credentials_id]


async def test_login_rejects_new_external_identity_without_verified_email() -> None:
    repository = FakeCredentialRepository()
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
    )

    with pytest.raises(AuthenticationError):
        await command_use_case.execute(LoginCommand(provider_token="firebase-id-token"))

    assert repository.credentials_by_identity == {}
    assert repository.refresh_token_hashes == {}


async def test_login_links_verified_email_to_existing_credentials() -> None:
    repository = FakeCredentialRepository()
    existing_credentials = UserCredential.create(
        user_id=uuid4(),
        credentials_id=uuid4(),
        role="user",
    )
    repository.credentials_by_identity[("google", "google-uid")] = existing_credentials
    repository.credentials_by_verified_email["user@example.com"] = existing_credentials
    command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(
            ExternalIdentity.create(
                issuer="apple",
                subject="apple-uid",
                provider="apple",
                email="user@example.com",
                name="테스트 사용자",
                email_verified=True,
            )
        ),
        repository=repository,
    )

    await command_use_case.execute(LoginCommand(provider_token="firebase-id-token"))

    assert repository.credentials_by_identity[("apple", "apple-uid")] == existing_credentials
    assert len(repository.credentials_by_identity) == 2
    assert repository.saved_identities == [
        ("apple", "apple-uid", "apple", "user@example.com", "테스트 사용자")
    ]
    assert repository.login_records == [existing_credentials.credentials_id]


async def test_login_does_not_store_refresh_token_when_identity_verification_fails() -> None:
    repository = FakeCredentialRepository()
    command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(error=AuthenticationError()),
        repository=repository,
    )

    with pytest.raises(AuthenticationError):
        await command_use_case.execute(LoginCommand(provider_token="bad-token"))

    assert repository.credentials_by_identity == {}
    assert repository.refresh_token_hashes == {}
