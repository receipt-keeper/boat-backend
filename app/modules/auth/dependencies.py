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
from app.modules.auth.application.ports.token_issuer import (
    AccessTokenIssuer,
    AccessTokenVerifier,
    RefreshTokenHasher,
    RefreshTokenIssuer,
)
from app.modules.auth.application.ports.user_provisioner import (
    ProvisionedUser,
    UserProvisioner,
    UserProvisioningRequest,
)
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
from app.modules.auth.infrastructure.tokens.jwt import JwtAccessTokenService
from app.modules.auth.infrastructure.tokens.opaque_refresh_token import OpaqueRefreshTokenIssuer
from app.modules.users.application.commands.resolve_user_for_login.command import (
    ResolveUserForLoginCommand,
)
from app.modules.users.application.commands.resolve_user_for_login.use_case import (
    ResolveUserForLoginCommandUseCase,
)
from app.modules.users.application.commands.withdrawal_cleanup.use_case import (
    WithdrawalCleanupCommandUseCase,
)
from app.modules.users.dependencies import (
    build_resolve_user_for_login_command_use_case,
    build_withdrawal_cleanup_command_use_case,
)


class _ProvisionUserPortAdapter(UserProvisioner):
    def __init__(
        self,
        command_use_case: ResolveUserForLoginCommandUseCase,
        *,
        initial_free_analysis_tokens: int = 0,
        default_profile_image_url: str | None = None,
    ) -> None:
        self._command_use_case = command_use_case
        self._initial_free_analysis_tokens = initial_free_analysis_tokens
        self._default_profile_image_url = default_profile_image_url

    async def provision(self, *, request: UserProvisioningRequest) -> ProvisionedUser:
        result = await self._command_use_case.execute(
            ResolveUserForLoginCommand(
                name=request.name,
                email=request.normalized_email,
                profile_image_url=request.profile_image_url or self._default_profile_image_url,
                initial_free_analysis_tokens=self._initial_free_analysis_tokens,
                terms_version=request.terms_version,
                privacy_version=request.privacy_version,
                terms_accepted=request.terms_accepted,
                privacy_accepted=request.privacy_accepted,
                marketing_consent=request.marketing_consent,
            )
        )
        return ProvisionedUser(user_id=result.user_id)


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


async def get_user_provisioner(
    session: AuthTransactionSessionDep,
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> UserProvisioner:
    command_use_case = build_resolve_user_for_login_command_use_case(session)
    return _ProvisionUserPortAdapter(
        command_use_case,
        initial_free_analysis_tokens=settings.initial_free_analysis_tokens,
        default_profile_image_url=settings.default_profile_image_url,
    )


async def get_withdrawal_cleanup_command_use_case(
    session: AuthTransactionSessionDep,
) -> WithdrawalCleanupCommandUseCase:
    return build_withdrawal_cleanup_command_use_case(session)


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
    withdrawal_cleanup_command_use_case: Annotated[
        WithdrawalCleanupCommandUseCase,
        Depends(get_withdrawal_cleanup_command_use_case),
    ],
) -> WithdrawAccountCommandUseCase:
    return WithdrawAccountCommandUseCase(
        credential_repository=credential_repository,
        withdrawal_cleanup_command_use_case=withdrawal_cleanup_command_use_case,
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
