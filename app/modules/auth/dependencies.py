from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.dependencies import get_request_settings
from app.core.config.settings import Settings
from app.modules.auth.application.commands.login.use_case import LoginCommandUseCase
from app.modules.auth.application.commands.logout.use_case import LogoutCommandUseCase
from app.modules.auth.application.commands.refresh.use_case import RefreshTokenCommandUseCase
from app.modules.auth.application.commands.withdraw.use_case import WithdrawAccountCommandUseCase
from app.modules.auth.application.ports.credential_repository import (
    CredentialRepository,
    CredentialRepositoryProvider,
)
from app.modules.auth.application.ports.external_identity_login_synchronizer import (
    ExternalIdentityLoginSynchronizer,
)
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.application.ports.push_cleanup import PushCleanup
from app.modules.auth.application.ports.token_issuer import (
    AccessTokenIssuer,
    AccessTokenVerifier,
    RefreshTokenHasher,
    RefreshTokenIssuer,
)
from app.modules.auth.application.ports.user_provisioner import ProvisionedUser, UserProvisioner
from app.modules.auth.application.queries.current_principal.use_case import (
    CurrentPrincipalQueryUseCase,
)
from app.modules.auth.infrastructure.identity_providers.firebase import (
    FirebaseExternalIdentityVerifier,
)
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.persistence.external_identity_login_synchronizer import (
    SqlAlchemyExternalIdentityLoginSynchronizer,
)
from app.modules.auth.infrastructure.push_cleanup import NoOpPushCleanup
from app.modules.auth.infrastructure.tokens.jwt import JwtAccessTokenService
from app.modules.auth.infrastructure.tokens.opaque_refresh_token import OpaqueRefreshTokenIssuer
from app.modules.users.application.commands.delete.use_case import DeleteUserCommandUseCase
from app.modules.users.application.commands.provision.command import ProvisionUserCommand
from app.modules.users.application.commands.provision.use_case import ProvisionUserCommandUseCase
from app.modules.users.dependencies import (
    build_delete_user_command_use_case,
    build_provision_user_command_use_case,
)


class _ProvisionUserPortAdapter(UserProvisioner):
    def __init__(self, command_use_case: ProvisionUserCommandUseCase) -> None:
        self._command_use_case = command_use_case

    async def provision(self, *, name: str | None, email: str | None) -> ProvisionedUser:
        user = await self._command_use_case.execute(ProvisionUserCommand(name=name, email=email))
        return ProvisionedUser(user_id=user.user_id)


class RequestCredentialRepositoryProvider(CredentialRepositoryProvider):
    def __init__(self, request: Request) -> None:
        self._request = request

    def get(self) -> CredentialRepository:
        return SqlAlchemyCredentialRepository(self._request.app.state.session_factory)


async def get_auth_transaction_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


AuthTransactionSessionDep = Annotated[AsyncSession, Depends(get_auth_transaction_session)]


async def get_credential_repository(
    session: AuthTransactionSessionDep,
) -> CredentialRepository:
    return SqlAlchemyCredentialRepository(session)


async def get_current_principal_credential_repository_provider(
    request: Request,
) -> CredentialRepositoryProvider:
    return RequestCredentialRepositoryProvider(request)


async def get_external_identity_login_synchronizer(
    session: AuthTransactionSessionDep,
) -> ExternalIdentityLoginSynchronizer:
    return SqlAlchemyExternalIdentityLoginSynchronizer(session)


async def get_user_provisioner(session: AuthTransactionSessionDep) -> UserProvisioner:
    command_use_case = build_provision_user_command_use_case(session)
    return _ProvisionUserPortAdapter(command_use_case)


async def get_delete_user_command_use_case(
    session: AuthTransactionSessionDep,
) -> DeleteUserCommandUseCase:
    return build_delete_user_command_use_case(session)


async def get_push_cleanup() -> PushCleanup:
    return NoOpPushCleanup()


async def get_external_identity_verifier(
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> ExternalIdentityVerifier:
    return FirebaseExternalIdentityVerifier.from_settings(settings)


async def get_access_token_issuer(
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> AccessTokenIssuer:
    return JwtAccessTokenService.from_settings(settings)


async def get_access_token_verifier(
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> AccessTokenVerifier:
    return JwtAccessTokenService.from_settings(settings)


async def get_refresh_token_issuer(
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> RefreshTokenIssuer:
    return OpaqueRefreshTokenIssuer(
        pepper=settings.refresh_token_pepper,
        expires_days=settings.refresh_token_expires_days,
    )


async def get_refresh_token_hasher(
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> RefreshTokenHasher:
    return OpaqueRefreshTokenIssuer(
        pepper=settings.refresh_token_pepper,
        expires_days=settings.refresh_token_expires_days,
    )


async def get_login_command_use_case(
    credential_repository: Annotated[CredentialRepository, Depends(get_credential_repository)],
    login_synchronizer: Annotated[
        ExternalIdentityLoginSynchronizer,
        Depends(get_external_identity_login_synchronizer),
    ],
    identity_verifier: Annotated[
        ExternalIdentityVerifier,
        Depends(get_external_identity_verifier),
    ],
    user_provisioner: Annotated[UserProvisioner, Depends(get_user_provisioner)],
    access_token_issuer: Annotated[AccessTokenIssuer, Depends(get_access_token_issuer)],
    refresh_token_issuer: Annotated[
        RefreshTokenIssuer,
        Depends(get_refresh_token_issuer),
    ],
) -> LoginCommandUseCase:
    return LoginCommandUseCase(
        identity_verifier=identity_verifier,
        login_synchronizer=login_synchronizer,
        credential_repository=credential_repository,
        user_provisioner=user_provisioner,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
    )


async def get_refresh_token_command_use_case(
    credential_repository: Annotated[CredentialRepository, Depends(get_credential_repository)],
    access_token_issuer: Annotated[AccessTokenIssuer, Depends(get_access_token_issuer)],
    refresh_token_issuer: Annotated[
        RefreshTokenIssuer,
        Depends(get_refresh_token_issuer),
    ],
    refresh_token_hasher: Annotated[
        RefreshTokenHasher,
        Depends(get_refresh_token_hasher),
    ],
) -> RefreshTokenCommandUseCase:
    return RefreshTokenCommandUseCase(
        credential_repository=credential_repository,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
        refresh_token_hasher=refresh_token_hasher,
    )


async def get_logout_command_use_case(
    credential_repository: Annotated[CredentialRepository, Depends(get_credential_repository)],
    refresh_token_hasher: Annotated[
        RefreshTokenHasher,
        Depends(get_refresh_token_hasher),
    ],
) -> LogoutCommandUseCase:
    return LogoutCommandUseCase(
        credential_repository=credential_repository,
        refresh_token_hasher=refresh_token_hasher,
    )


async def get_current_principal_query_use_case(
    access_token_verifier: Annotated[AccessTokenVerifier, Depends(get_access_token_verifier)],
    credential_repository_provider: Annotated[
        CredentialRepositoryProvider,
        Depends(get_current_principal_credential_repository_provider),
    ],
) -> CurrentPrincipalQueryUseCase:
    return CurrentPrincipalQueryUseCase(
        access_token_verifier=access_token_verifier,
        credential_repository_provider=credential_repository_provider,
    )


async def get_withdraw_account_command_use_case(
    credential_repository: Annotated[CredentialRepository, Depends(get_credential_repository)],
    delete_user_command_use_case: Annotated[
        DeleteUserCommandUseCase,
        Depends(get_delete_user_command_use_case),
    ],
    push_cleanup: Annotated[PushCleanup, Depends(get_push_cleanup)],
) -> WithdrawAccountCommandUseCase:
    return WithdrawAccountCommandUseCase(
        credential_repository=credential_repository,
        delete_user_command_use_case=delete_user_command_use_case,
        push_cleanup=push_cleanup,
    )


LoginCommandUseCaseDep = Annotated[LoginCommandUseCase, Depends(get_login_command_use_case)]
RefreshTokenCommandUseCaseDep = Annotated[
    RefreshTokenCommandUseCase,
    Depends(get_refresh_token_command_use_case),
]
LogoutCommandUseCaseDep = Annotated[LogoutCommandUseCase, Depends(get_logout_command_use_case)]
CurrentPrincipalQueryUseCaseDep = Annotated[
    CurrentPrincipalQueryUseCase,
    Depends(get_current_principal_query_use_case),
]
WithdrawAccountCommandUseCaseDep = Annotated[
    WithdrawAccountCommandUseCase,
    Depends(get_withdraw_account_command_use_case),
]
