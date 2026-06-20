from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.users.application.commands.delete.use_case import DeleteUserCommandUseCase
from app.modules.users.application.commands.delete_push_token.use_case import (
    DeletePushTokenCommandUseCase,
)
from app.modules.users.application.commands.provision.use_case import ProvisionUserCommandUseCase
from app.modules.users.application.commands.register_push_token.use_case import (
    RegisterPushTokenCommandUseCase,
)
from app.modules.users.application.commands.resolve_user_for_login.use_case import (
    ResolveUserForLoginCommandUseCase,
)
from app.modules.users.application.commands.update_settings.use_case import (
    UpdateSettingsCommandUseCase,
)
from app.modules.users.application.commands.withdrawal_cleanup.use_case import (
    WithdrawalCleanupCommandUseCase,
)
from app.modules.users.application.ports.user_repository import UserRepository
from app.modules.users.application.queries.current_user_profile.use_case import (
    CurrentUserProfileQueryUseCase,
)
from app.modules.users.infrastructure.persistence.repository import SqlAlchemyUserRepository

SessionProvider = AsyncSession | async_sessionmaker[AsyncSession]


def build_provision_user_command_use_case(
    session_provider: SessionProvider,
) -> ProvisionUserCommandUseCase:
    return ProvisionUserCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session_provider),
    )


def build_delete_user_command_use_case(
    session_provider: SessionProvider,
) -> DeleteUserCommandUseCase:
    return DeleteUserCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session_provider),
    )


def build_current_user_profile_query_use_case(
    session_provider: SessionProvider,
) -> CurrentUserProfileQueryUseCase:
    return CurrentUserProfileQueryUseCase(
        user_repository=SqlAlchemyUserRepository(session_provider),
    )


def build_update_settings_command_use_case(
    session_provider: SessionProvider,
) -> UpdateSettingsCommandUseCase:
    return UpdateSettingsCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session_provider),
    )


def build_register_push_token_command_use_case(
    session_provider: SessionProvider,
) -> RegisterPushTokenCommandUseCase:
    return RegisterPushTokenCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session_provider),
    )


def build_delete_push_token_command_use_case(
    session_provider: SessionProvider,
) -> DeletePushTokenCommandUseCase:
    return DeletePushTokenCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session_provider),
    )


def build_withdrawal_cleanup_command_use_case(
    session_provider: SessionProvider,
) -> WithdrawalCleanupCommandUseCase:
    return WithdrawalCleanupCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session_provider),
    )


def build_resolve_user_for_login_command_use_case(
    session_provider: SessionProvider,
) -> ResolveUserForLoginCommandUseCase:
    return ResolveUserForLoginCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session_provider),
    )


async def get_user_repository(request: Request) -> UserRepository:
    return SqlAlchemyUserRepository(request.app.state.session_factory)


async def get_provision_user_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProvisionUserCommandUseCase:
    return ProvisionUserCommandUseCase(user_repository=user_repository)


async def get_delete_user_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> DeleteUserCommandUseCase:
    return DeleteUserCommandUseCase(user_repository=user_repository)


async def get_current_user_profile_query_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> CurrentUserProfileQueryUseCase:
    return CurrentUserProfileQueryUseCase(user_repository=user_repository)


async def get_update_settings_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> UpdateSettingsCommandUseCase:
    return UpdateSettingsCommandUseCase(user_repository=user_repository)


async def get_register_push_token_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> RegisterPushTokenCommandUseCase:
    return RegisterPushTokenCommandUseCase(user_repository=user_repository)


async def get_delete_push_token_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> DeletePushTokenCommandUseCase:
    return DeletePushTokenCommandUseCase(user_repository=user_repository)


async def get_withdrawal_cleanup_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> WithdrawalCleanupCommandUseCase:
    return WithdrawalCleanupCommandUseCase(user_repository=user_repository)


async def get_resolve_user_for_login_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> ResolveUserForLoginCommandUseCase:
    return ResolveUserForLoginCommandUseCase(user_repository=user_repository)


ProvisionUserCommandUseCaseDep = Annotated[
    ProvisionUserCommandUseCase,
    Depends(get_provision_user_command_use_case),
]
DeleteUserCommandUseCaseDep = Annotated[
    DeleteUserCommandUseCase,
    Depends(get_delete_user_command_use_case),
]
CurrentUserProfileQueryUseCaseDep = Annotated[
    CurrentUserProfileQueryUseCase,
    Depends(get_current_user_profile_query_use_case),
]
UpdateSettingsCommandUseCaseDep = Annotated[
    UpdateSettingsCommandUseCase,
    Depends(get_update_settings_command_use_case),
]
RegisterPushTokenCommandUseCaseDep = Annotated[
    RegisterPushTokenCommandUseCase,
    Depends(get_register_push_token_command_use_case),
]
DeletePushTokenCommandUseCaseDep = Annotated[
    DeletePushTokenCommandUseCase,
    Depends(get_delete_push_token_command_use_case),
]
WithdrawalCleanupCommandUseCaseDep = Annotated[
    WithdrawalCleanupCommandUseCase,
    Depends(get_withdrawal_cleanup_command_use_case),
]
ResolveUserForLoginCommandUseCaseDep = Annotated[
    ResolveUserForLoginCommandUseCase,
    Depends(get_resolve_user_for_login_command_use_case),
]
