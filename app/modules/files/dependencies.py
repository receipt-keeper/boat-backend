from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import column, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.unit_of_work import UnitOfWork
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.exceptions import ConflictError
from app.modules.files.application.commands.delete_file.use_case import (
    DeleteFileCommandUseCase,
)
from app.modules.files.application.commands.upload_file.use_case import (
    UploadFileCommandUseCase,
)
from app.modules.files.application.ports.file_reference_guard import FileReferenceGuard
from app.modules.files.application.ports.file_repository import FileRepository
from app.modules.files.application.ports.object_storage import ObjectStorage
from app.modules.files.application.queries.get_file.use_case import GetFileQueryUseCase
from app.modules.files.application.queries.open_file_content.use_case import (
    OpenFileContentQueryUseCase,
)
from app.modules.files.infrastructure.persistence.repository import SqlAlchemyFileRepository
from app.modules.files.infrastructure.storage.local import LocalObjectStorage


class UserProfileImageReferenceGuard(FileReferenceGuard):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_not_referenced(self, *, file_id: UUID) -> None:
        profile_image_url = f"/files/{file_id}/content"
        users = table("users", column("id"), column("profile_image_url"))
        statement = select(users.c.id).where(users.c.profile_image_url == profile_image_url)
        if await self._session.scalar(statement) is not None:
            raise ConflictError("프로필 이미지로 사용 중인 파일은 삭제할 수 없습니다.")


def build_file_repository(session: AsyncSession) -> FileRepository:
    return SqlAlchemyFileRepository(session)


def build_object_storage(root: str) -> ObjectStorage:
    return LocalObjectStorage(root=root)


async def get_file_repository(
    session: AsyncSessionDep,
) -> FileRepository:
    return build_file_repository(session)


async def get_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


async def get_file_reference_guard(session: AsyncSessionDep) -> FileReferenceGuard:
    return UserProfileImageReferenceGuard(session)


def get_local_file_storage_root(request: Request) -> str:
    return request.app.state.settings.file_storage_root


async def get_object_storage(
    root: Annotated[str, Depends(get_local_file_storage_root)],
) -> ObjectStorage:
    return build_object_storage(root)


async def get_upload_file_command_use_case(
    repository: Annotated[FileRepository, Depends(get_file_repository)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> UploadFileCommandUseCase:
    return UploadFileCommandUseCase(
        repository=repository,
        storage=storage,
        unit_of_work=unit_of_work,
    )


async def get_get_file_query_use_case(
    repository: Annotated[FileRepository, Depends(get_file_repository)],
) -> GetFileQueryUseCase:
    return GetFileQueryUseCase(repository=repository)


async def get_open_file_content_query_use_case(
    repository: Annotated[FileRepository, Depends(get_file_repository)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> OpenFileContentQueryUseCase:
    return OpenFileContentQueryUseCase(repository=repository, storage=storage)


async def get_delete_file_command_use_case(
    repository: Annotated[FileRepository, Depends(get_file_repository)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
    reference_guard: Annotated[FileReferenceGuard, Depends(get_file_reference_guard)],
) -> DeleteFileCommandUseCase:
    return DeleteFileCommandUseCase(
        repository=repository,
        storage=storage,
        unit_of_work=unit_of_work,
        reference_guard=reference_guard,
    )


UploadFileCommandUseCaseDep = Annotated[
    UploadFileCommandUseCase,
    Depends(get_upload_file_command_use_case),
]
GetFileQueryUseCaseDep = Annotated[
    GetFileQueryUseCase,
    Depends(get_get_file_query_use_case),
]
OpenFileContentQueryUseCaseDep = Annotated[
    OpenFileContentQueryUseCase,
    Depends(get_open_file_content_query_use_case),
]
DeleteFileCommandUseCaseDep = Annotated[
    DeleteFileCommandUseCase,
    Depends(get_delete_file_command_use_case),
]
