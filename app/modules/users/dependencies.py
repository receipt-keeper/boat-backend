from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import column, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.unit_of_work import UnitOfWork
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.exceptions import ConflictError, NotFoundError
from app.modules.files.application.ports.file_reference_guard import FileReferenceGuard
from app.modules.files.application.ports.file_repository import FileRepository
from app.modules.files.dependencies import get_file_repository
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
from app.modules.users.application.commands.update_profile_image.use_case import (
    UpdateProfileImageCommandUseCase,
)
from app.modules.users.application.commands.update_settings.use_case import (
    UpdateSettingsCommandUseCase,
)
from app.modules.users.application.commands.withdrawal_cleanup.use_case import (
    WithdrawalCleanupCommandUseCase,
)
from app.modules.users.application.ports.profile_image_file_validator import (
    ProfileImageFileValidator,
)
from app.modules.users.application.ports.user_repository import UserRepository
from app.modules.users.application.queries.current_user_profile.use_case import (
    CurrentUserProfileQueryUseCase,
)
from app.modules.users.infrastructure.persistence.repository import SqlAlchemyUserRepository


class FileRepositoryProfileImageFileValidator(ProfileImageFileValidator):
    def __init__(self, file_repository: FileRepository) -> None:
        self._file_repository = file_repository

    async def ensure_owned_image_file(self, *, user_id: UUID, file_id: UUID) -> None:
        stored_file = await self._file_repository.find_by_id_for_user(
            file_id=file_id,
            user_id=user_id,
        )
        if stored_file is None:
            raise NotFoundError("파일을 찾을 수 없습니다.")


class UserProfileImageFileReferenceGuard(FileReferenceGuard):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_not_referenced(self, *, file_id: UUID) -> None:
        profile_image_url = f"/files/{file_id}/content"
        users = table("users", column("id"), column("profile_image_url"))
        statement = select(users.c.id).where(users.c.profile_image_url == profile_image_url)
        if await self._session.scalar(statement) is not None:
            raise ConflictError("프로필 이미지로 사용 중인 파일은 삭제할 수 없습니다.")


def build_provision_user_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> ProvisionUserCommandUseCase:
    return ProvisionUserCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        unit_of_work=unit_of_work,
    )


def build_delete_user_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> DeleteUserCommandUseCase:
    return DeleteUserCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        unit_of_work=unit_of_work,
    )


def build_current_user_profile_query_use_case(
    session: AsyncSession,
) -> CurrentUserProfileQueryUseCase:
    return CurrentUserProfileQueryUseCase(
        user_repository=SqlAlchemyUserRepository(session),
    )


def build_update_settings_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> UpdateSettingsCommandUseCase:
    return UpdateSettingsCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        unit_of_work=unit_of_work,
    )


def build_update_profile_image_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
    profile_image_file_validator: ProfileImageFileValidator,
) -> UpdateProfileImageCommandUseCase:
    return UpdateProfileImageCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        profile_image_file_validator=profile_image_file_validator,
        unit_of_work=unit_of_work,
    )


def build_register_push_token_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> RegisterPushTokenCommandUseCase:
    return RegisterPushTokenCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        unit_of_work=unit_of_work,
    )


def build_delete_push_token_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> DeletePushTokenCommandUseCase:
    return DeletePushTokenCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        unit_of_work=unit_of_work,
    )


def build_withdrawal_cleanup_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> WithdrawalCleanupCommandUseCase:
    return WithdrawalCleanupCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        unit_of_work=unit_of_work,
    )


def build_resolve_user_for_login_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> ResolveUserForLoginCommandUseCase:
    return ResolveUserForLoginCommandUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        unit_of_work=unit_of_work,
    )


async def get_user_repository(session: AsyncSessionDep) -> UserRepository:
    return SqlAlchemyUserRepository(session)


async def get_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


async def get_profile_image_file_validator(
    file_repository: Annotated[FileRepository, Depends(get_file_repository)],
) -> ProfileImageFileValidator:
    return FileRepositoryProfileImageFileValidator(file_repository)


async def get_profile_image_file_reference_guard(session: AsyncSessionDep) -> FileReferenceGuard:
    return UserProfileImageFileReferenceGuard(session)


async def get_provision_user_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> ProvisionUserCommandUseCase:
    return ProvisionUserCommandUseCase(user_repository=user_repository, unit_of_work=unit_of_work)


async def get_delete_user_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> DeleteUserCommandUseCase:
    return DeleteUserCommandUseCase(user_repository=user_repository, unit_of_work=unit_of_work)


async def get_current_user_profile_query_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> CurrentUserProfileQueryUseCase:
    return CurrentUserProfileQueryUseCase(user_repository=user_repository)


async def get_update_settings_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> UpdateSettingsCommandUseCase:
    return UpdateSettingsCommandUseCase(user_repository=user_repository, unit_of_work=unit_of_work)


async def get_update_profile_image_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    profile_image_file_validator: Annotated[
        ProfileImageFileValidator,
        Depends(get_profile_image_file_validator),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> UpdateProfileImageCommandUseCase:
    return UpdateProfileImageCommandUseCase(
        user_repository=user_repository,
        profile_image_file_validator=profile_image_file_validator,
        unit_of_work=unit_of_work,
    )


async def get_register_push_token_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> RegisterPushTokenCommandUseCase:
    return RegisterPushTokenCommandUseCase(
        user_repository=user_repository,
        unit_of_work=unit_of_work,
    )


async def get_delete_push_token_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> DeletePushTokenCommandUseCase:
    return DeletePushTokenCommandUseCase(user_repository=user_repository, unit_of_work=unit_of_work)


async def get_withdrawal_cleanup_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> WithdrawalCleanupCommandUseCase:
    return WithdrawalCleanupCommandUseCase(
        user_repository=user_repository,
        unit_of_work=unit_of_work,
    )


async def get_resolve_user_for_login_command_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> ResolveUserForLoginCommandUseCase:
    return ResolveUserForLoginCommandUseCase(
        user_repository=user_repository,
        unit_of_work=unit_of_work,
    )


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
UpdateProfileImageCommandUseCaseDep = Annotated[
    UpdateProfileImageCommandUseCase,
    Depends(get_update_profile_image_command_use_case),
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
