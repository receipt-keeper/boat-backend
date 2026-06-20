from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.users.application.commands.delete.use_case import DeleteUserCommandUseCase
from app.modules.users.application.commands.provision.use_case import ProvisionUserCommandUseCase
from app.modules.users.application.ports.user_repository import UserRepository
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


ProvisionUserCommandUseCaseDep = Annotated[
    ProvisionUserCommandUseCase,
    Depends(get_provision_user_command_use_case),
]
DeleteUserCommandUseCaseDep = Annotated[
    DeleteUserCommandUseCase,
    Depends(get_delete_user_command_use_case),
]
