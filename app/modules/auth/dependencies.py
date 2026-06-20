from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.dependencies import get_request_settings
from app.core.config.settings import Settings
from app.modules.auth.application.authorize.use_case import AuthorizeUseCase
from app.modules.auth.application.login.use_case import LoginUseCase
from app.modules.auth.application.logout.use_case import LogoutUseCase
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
from app.modules.auth.application.refresh.use_case import RefreshTokenUseCase
from app.modules.auth.application.withdraw.use_case import WithdrawAccountUseCase
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
from app.modules.users.application.delete.use_case import DeleteUserUseCase
from app.modules.users.application.provision.schemas import ProvisionUserCommand
from app.modules.users.application.provision.use_case import ProvisionUserUseCase
from app.modules.users.dependencies import build_delete_user_use_case, build_provision_user_use_case


class UsersModuleUserProvisioner(UserProvisioner):
    def __init__(self, use_case: ProvisionUserUseCase) -> None:
        self._use_case = use_case

    async def provision(self, *, name: str | None, email: str | None) -> ProvisionedUser:
        user = await self._use_case.execute(ProvisionUserCommand(name=name, email=email))
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


async def get_authorize_credential_repository_provider(
    request: Request,
) -> CredentialRepositoryProvider:
    return RequestCredentialRepositoryProvider(request)


async def get_external_identity_login_synchronizer(
    session: AuthTransactionSessionDep,
) -> ExternalIdentityLoginSynchronizer:
    return SqlAlchemyExternalIdentityLoginSynchronizer(session)


async def get_user_provisioner(session: AuthTransactionSessionDep) -> UserProvisioner:
    use_case = build_provision_user_use_case(session)
    return UsersModuleUserProvisioner(use_case)


async def get_delete_user_use_case(session: AuthTransactionSessionDep) -> DeleteUserUseCase:
    return build_delete_user_use_case(session)


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


async def get_login_use_case(
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
) -> LoginUseCase:
    return LoginUseCase(
        identity_verifier=identity_verifier,
        login_synchronizer=login_synchronizer,
        credential_repository=credential_repository,
        user_provisioner=user_provisioner,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
    )


async def get_refresh_token_use_case(
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
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(
        credential_repository=credential_repository,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
        refresh_token_hasher=refresh_token_hasher,
    )


async def get_logout_use_case(
    credential_repository: Annotated[CredentialRepository, Depends(get_credential_repository)],
    refresh_token_hasher: Annotated[
        RefreshTokenHasher,
        Depends(get_refresh_token_hasher),
    ],
) -> LogoutUseCase:
    return LogoutUseCase(
        credential_repository=credential_repository,
        refresh_token_hasher=refresh_token_hasher,
    )


async def get_authorize_use_case(
    access_token_verifier: Annotated[AccessTokenVerifier, Depends(get_access_token_verifier)],
    credential_repository_provider: Annotated[
        CredentialRepositoryProvider,
        Depends(get_authorize_credential_repository_provider),
    ],
) -> AuthorizeUseCase:
    return AuthorizeUseCase(
        access_token_verifier=access_token_verifier,
        credential_repository_provider=credential_repository_provider,
    )


async def get_withdraw_account_use_case(
    credential_repository: Annotated[CredentialRepository, Depends(get_credential_repository)],
    delete_user_use_case: Annotated[DeleteUserUseCase, Depends(get_delete_user_use_case)],
    push_cleanup: Annotated[PushCleanup, Depends(get_push_cleanup)],
) -> WithdrawAccountUseCase:
    return WithdrawAccountUseCase(
        credential_repository=credential_repository,
        delete_user_use_case=delete_user_use_case,
        push_cleanup=push_cleanup,
    )


LoginUseCaseDep = Annotated[LoginUseCase, Depends(get_login_use_case)]
RefreshTokenUseCaseDep = Annotated[RefreshTokenUseCase, Depends(get_refresh_token_use_case)]
LogoutUseCaseDep = Annotated[LogoutUseCase, Depends(get_logout_use_case)]
AuthorizeUseCaseDep = Annotated[AuthorizeUseCase, Depends(get_authorize_use_case)]
WithdrawAccountUseCaseDep = Annotated[
    WithdrawAccountUseCase,
    Depends(get_withdraw_account_use_case),
]
