from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.users.application.delete.use_case import DeleteUserUseCase
from app.modules.users.application.ports.user_repository import UserRepository
from app.modules.users.application.provision.use_case import ProvisionUserUseCase
from app.modules.users.infrastructure.persistence.repository import SqlAlchemyUserRepository

SessionProvider = AsyncSession | async_sessionmaker[AsyncSession]


def build_provision_user_use_case(session_provider: SessionProvider) -> ProvisionUserUseCase:
    return ProvisionUserUseCase(
        user_repository=SqlAlchemyUserRepository(session_provider),
    )


def build_delete_user_use_case(session_provider: SessionProvider) -> DeleteUserUseCase:
    return DeleteUserUseCase(
        user_repository=SqlAlchemyUserRepository(session_provider),
    )


async def get_user_repository(request: Request) -> UserRepository:
    return SqlAlchemyUserRepository(request.app.state.session_factory)


async def get_provision_user_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProvisionUserUseCase:
    return ProvisionUserUseCase(user_repository=user_repository)


ProvisionUserUseCaseDep = Annotated[ProvisionUserUseCase, Depends(get_provision_user_use_case)]
