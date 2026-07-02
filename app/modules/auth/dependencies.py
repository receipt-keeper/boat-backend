from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.core.application.unit_of_work import DeferredCommitUnitOfWork, UnitOfWork
from app.core.config.dependencies import get_request_settings
from app.core.config.settings import Settings
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.auth.application.commands.login.use_case import LoginCommandUseCase
from app.modules.auth.application.commands.logout.use_case import LogoutCommandUseCase
from app.modules.auth.application.commands.refresh.use_case import RefreshTokenCommandUseCase
from app.modules.auth.application.commands.signup.use_case import SignupCommandUseCase
from app.modules.auth.application.commands.withdraw.use_case import WithdrawAccountCommandUseCase
from app.modules.auth.application.ports.credential_repository import (
    ActiveSessionChecker,
    CredentialRepository,
)
from app.modules.auth.application.ports.credit_lifecycle import (
    CreditInitializer,
    CreditWithdrawalCleaner,
)
from app.modules.auth.application.ports.external_identity_login_synchronizer import (
    ExternalIdentityLoginSynchronizer,
)
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.application.ports.notification_settings_initializer import (
    NotificationSettingsInitializer,
)
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
from app.modules.auth.dependency_adapters import (
    CreditInitializerAdapter,
    CreditWithdrawalCleanerAdapter,
    NotificationSettingsInitializerAdapter,
    RequestActiveSessionChecker,
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
from app.modules.credits.dependencies import (
    build_delete_user_credits_command_use_case,
    build_grant_credit_command_use_case,
)
from app.modules.notifications.dependencies import (
    build_update_notification_settings_command_use_case,
)
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

SettingsDep = Annotated[Settings, Depends(get_request_settings)]


@dataclass(frozen=True, slots=True)
class ProvisionUserPortAdapter(UserProvisioner):
    command_use_case: ResolveUserForLoginCommandUseCase
    default_profile_image_url: str | None = None

    async def provision(self, *, request: UserProvisioningRequest) -> ProvisionedUser:
        result = await self.command_use_case.execute(
            ResolveUserForLoginCommand(
                name=request.name,
                email=request.email,
                profile_image_url=request.profile_image_url or self.default_profile_image_url,
                terms_version=request.terms_version,
                privacy_version=request.privacy_version,
                terms_accepted=request.terms_accepted,
                privacy_accepted=request.privacy_accepted,
            )
        )
        return ProvisionedUser(user_id=result.user_id)


async def get_credential_repository(session: AsyncSessionDep) -> CredentialRepository:
    return SqlAlchemyCredentialRepository(session)


async def get_active_session_checker(request: Request) -> ActiveSessionChecker:
    return RequestActiveSessionChecker(request)


async def get_external_identity_login_synchronizer(
    session: AsyncSessionDep,
) -> ExternalIdentityLoginSynchronizer:
    return SqlAlchemyExternalIdentityLoginSynchronizer(session)


async def get_external_identity_verifier(settings: SettingsDep) -> ExternalIdentityVerifier:
    return FirebaseExternalIdentityVerifier.from_settings(settings)


async def get_access_token_issuer(settings: SettingsDep) -> AccessTokenIssuer:
    return JwtAccessTokenService.from_settings(settings)


async def get_access_token_verifier(settings: SettingsDep) -> AccessTokenVerifier:
    return JwtAccessTokenService.from_settings(settings)


async def get_refresh_token_issuer(settings: SettingsDep) -> RefreshTokenIssuer:
    return OpaqueRefreshTokenIssuer(
        pepper=settings.refresh_token_pepper,
        expires_days=settings.refresh_token_expires_days,
    )


async def get_refresh_token_hasher(settings: SettingsDep) -> RefreshTokenHasher:
    return OpaqueRefreshTokenIssuer(
        pepper=settings.refresh_token_pepper,
        expires_days=settings.refresh_token_expires_days,
    )


async def get_user_provisioner(session: AsyncSessionDep, settings: SettingsDep) -> UserProvisioner:
    command_use_case = build_resolve_user_for_login_command_use_case(
        session,
        DeferredCommitUnitOfWork(),
    )
    return ProvisionUserPortAdapter(
        command_use_case,
        default_profile_image_url=settings.default_profile_image_url,
    )


async def get_notification_settings_initializer(
    session: AsyncSessionDep,
) -> NotificationSettingsInitializer:
    return NotificationSettingsInitializerAdapter(
        build_update_notification_settings_command_use_case(
            session,
            DeferredCommitUnitOfWork(),
        )
    )


async def get_credit_initializer(session: AsyncSessionDep) -> CreditInitializer:
    return CreditInitializerAdapter(
        build_grant_credit_command_use_case(
            session,
            DeferredCommitUnitOfWork(),
        )
    )


async def get_credit_withdrawal_cleaner(
    session: AsyncSessionDep,
) -> CreditWithdrawalCleaner:
    return CreditWithdrawalCleanerAdapter(
        build_delete_user_credits_command_use_case(
            session,
            DeferredCommitUnitOfWork(),
        )
    )


async def get_withdrawal_cleanup_command_use_case(
    session: AsyncSessionDep,
) -> WithdrawalCleanupCommandUseCase:
    return build_withdrawal_cleanup_command_use_case(session, DeferredCommitUnitOfWork())


async def get_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


CredentialRepositoryDep = Annotated[CredentialRepository, Depends(get_credential_repository)]
LoginSynchronizerDep = Annotated[
    ExternalIdentityLoginSynchronizer,
    Depends(get_external_identity_login_synchronizer),
]
IdentityVerifierDep = Annotated[ExternalIdentityVerifier, Depends(get_external_identity_verifier)]
AccessTokenIssuerDep = Annotated[AccessTokenIssuer, Depends(get_access_token_issuer)]
AccessTokenVerifierDep = Annotated[AccessTokenVerifier, Depends(get_access_token_verifier)]
RefreshTokenIssuerDep = Annotated[RefreshTokenIssuer, Depends(get_refresh_token_issuer)]
RefreshTokenHasherDep = Annotated[RefreshTokenHasher, Depends(get_refresh_token_hasher)]
UserProvisionerDep = Annotated[UserProvisioner, Depends(get_user_provisioner)]
NotificationInitializerDep = Annotated[
    NotificationSettingsInitializer,
    Depends(get_notification_settings_initializer),
]
CreditInitializerDep = Annotated[CreditInitializer, Depends(get_credit_initializer)]
CreditWithdrawalCleanerDep = Annotated[
    CreditWithdrawalCleaner,
    Depends(get_credit_withdrawal_cleaner),
]
UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_unit_of_work)]
ActiveSessionCheckerDep = Annotated[ActiveSessionChecker, Depends(get_active_session_checker)]
WithdrawalCleanupUseCaseDep = Annotated[
    WithdrawalCleanupCommandUseCase,
    Depends(get_withdrawal_cleanup_command_use_case),
]


async def get_login_command_use_case(
    credential_repository: CredentialRepositoryDep,
    login_synchronizer: LoginSynchronizerDep,
    identity_verifier: IdentityVerifierDep,
    access_token_issuer: AccessTokenIssuerDep,
    refresh_token_issuer: RefreshTokenIssuerDep,
    unit_of_work: UnitOfWorkDep,
) -> LoginCommandUseCase:
    return LoginCommandUseCase(
        identity_verifier=identity_verifier,
        login_synchronizer=login_synchronizer,
        credential_repository=credential_repository,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
        unit_of_work=unit_of_work,
    )


async def get_signup_command_use_case(
    credential_repository: CredentialRepositoryDep,
    identity_synchronizer: LoginSynchronizerDep,
    identity_verifier: IdentityVerifierDep,
    user_provisioner: UserProvisionerDep,
    notification_settings_initializer: NotificationInitializerDep,
    credit_initializer: CreditInitializerDep,
    access_token_issuer: AccessTokenIssuerDep,
    refresh_token_issuer: RefreshTokenIssuerDep,
    unit_of_work: UnitOfWorkDep,
) -> SignupCommandUseCase:
    return SignupCommandUseCase(
        identity_verifier=identity_verifier,
        identity_synchronizer=identity_synchronizer,
        credential_repository=credential_repository,
        user_provisioner=user_provisioner,
        notification_settings_initializer=notification_settings_initializer,
        credit_initializer=credit_initializer,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
        unit_of_work=unit_of_work,
    )


async def get_refresh_token_command_use_case(
    credential_repository: CredentialRepositoryDep,
    access_token_issuer: AccessTokenIssuerDep,
    refresh_token_issuer: RefreshTokenIssuerDep,
    refresh_token_hasher: RefreshTokenHasherDep,
    unit_of_work: UnitOfWorkDep,
) -> RefreshTokenCommandUseCase:
    return RefreshTokenCommandUseCase(
        credential_repository=credential_repository,
        access_token_issuer=access_token_issuer,
        refresh_token_issuer=refresh_token_issuer,
        refresh_token_hasher=refresh_token_hasher,
        unit_of_work=unit_of_work,
    )


async def get_logout_command_use_case(
    credential_repository: CredentialRepositoryDep,
    refresh_token_hasher: RefreshTokenHasherDep,
    unit_of_work: UnitOfWorkDep,
) -> LogoutCommandUseCase:
    return LogoutCommandUseCase(
        credential_repository=credential_repository,
        refresh_token_hasher=refresh_token_hasher,
        unit_of_work=unit_of_work,
    )


async def get_current_principal_query_use_case(
    access_token_verifier: AccessTokenVerifierDep,
    active_session_checker: ActiveSessionCheckerDep,
) -> CurrentPrincipalQueryUseCase:
    return CurrentPrincipalQueryUseCase(
        access_token_verifier=access_token_verifier,
        active_session_checker=active_session_checker,
    )


async def get_withdraw_account_command_use_case(
    credential_repository: CredentialRepositoryDep,
    withdrawal_cleanup_command_use_case: WithdrawalCleanupUseCaseDep,
    credit_withdrawal_cleaner: CreditWithdrawalCleanerDep,
    unit_of_work: UnitOfWorkDep,
) -> WithdrawAccountCommandUseCase:
    return WithdrawAccountCommandUseCase(
        credential_repository=credential_repository,
        withdrawal_cleanup_command_use_case=withdrawal_cleanup_command_use_case,
        credit_withdrawal_cleaner=credit_withdrawal_cleaner,
        unit_of_work=unit_of_work,
    )


LoginCommandUseCaseDep = Annotated[LoginCommandUseCase, Depends(get_login_command_use_case)]
SignupCommandUseCaseDep = Annotated[SignupCommandUseCase, Depends(get_signup_command_use_case)]
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
