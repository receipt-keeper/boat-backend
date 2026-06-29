from uuid import UUID

import pytest

from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.application.commands.logout.command import LogoutCommand
from app.modules.auth.application.commands.refresh.command import RefreshTokenCommand
from app.modules.auth.application.ports.credential_repository import ActiveSessionChecker
from app.modules.auth.application.queries.current_principal.query import CurrentPrincipalQuery
from app.modules.auth.application.queries.current_principal.use_case import (
    CurrentPrincipalQueryUseCase,
)
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.tests.credential_repository_fake import FakeCredentialRepository
from app.modules.auth.tests.service_fakes import (
    FakeExternalIdentityVerifier,
    build_access_token_issuer,
    build_login_command_use_case,
    build_logout_command_use_case,
    build_refresh_command_use_case,
)


class StaticActiveSessionChecker(ActiveSessionChecker):
    def __init__(self, repository: FakeCredentialRepository) -> None:
        self._repository = repository

    async def exists_active_session(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
        session_id: UUID,
    ) -> bool:
        return await self._repository.exists_active_session(
            user_id=user_id,
            credentials_id=credentials_id,
            session_id=session_id,
        )


def _registered_apple_identity(repository: FakeCredentialRepository) -> ExternalIdentity:
    identity = ExternalIdentity.create(
        issuer="apple",
        subject="firebase-uid",
        provider="apple",
        email="user@example.com",
        name=None,
        email_verified=True,
    )
    repository.seed_existing_external_identity(identity=identity)
    return identity


async def test_refresh_rotates_refresh_token_and_rejects_old_token() -> None:
    repository = FakeCredentialRepository()
    identity = _registered_apple_identity(repository)
    login_command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(identity),
        repository=repository,
    )
    refresh_command_use_case = build_refresh_command_use_case(repository=repository)
    first_pair = await login_command_use_case.execute(
        LoginCommand(provider_token="firebase-id-token")
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
    identity = _registered_apple_identity(repository)
    login_command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(identity),
        repository=repository,
    )
    logout_command_use_case = build_logout_command_use_case(repository=repository)
    tokens = await login_command_use_case.execute(LoginCommand(provider_token="firebase-id-token"))
    token_hash = next(iter(repository.refresh_token_hashes))

    await logout_command_use_case.execute(LogoutCommand(refresh_token=tokens.refresh_token))

    assert token_hash not in repository.refresh_token_hashes
    assert repository.revoked_hashes == [token_hash]


async def test_logout_invalidates_same_session_access_token() -> None:
    repository = FakeCredentialRepository()
    identity = _registered_apple_identity(repository)
    login_command_use_case = build_login_command_use_case(
        verifier=FakeExternalIdentityVerifier(identity),
        repository=repository,
    )
    current_principal_query_use_case = CurrentPrincipalQueryUseCase(
        access_token_verifier=build_access_token_issuer(),
        active_session_checker=StaticActiveSessionChecker(repository),
    )
    logout_command_use_case = build_logout_command_use_case(repository=repository)
    tokens = await login_command_use_case.execute(LoginCommand(provider_token="firebase-id-token"))

    principal = await current_principal_query_use_case.execute(
        CurrentPrincipalQuery(token=tokens.access_token)
    )
    await logout_command_use_case.execute(LogoutCommand(refresh_token=tokens.refresh_token))

    assert principal.credentials_id in repository.login_records
    with pytest.raises(AuthenticationError):
        await current_principal_query_use_case.execute(
            CurrentPrincipalQuery(token=tokens.access_token)
        )
