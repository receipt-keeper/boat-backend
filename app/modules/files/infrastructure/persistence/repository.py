from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.application.ports.file_repository import FileRepository
from app.modules.files.domain.model import File, FileObject, StoredFile
from app.modules.files.infrastructure.persistence import mapper, orm


class SqlAlchemyFileRepository(FileRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, *, file: File, file_object: FileObject) -> StoredFile:
        file_record = mapper.file_to_record(file)
        file_object_record = mapper.file_object_to_record(file_object)
        self._session.add(file_record)
        self._session.add(file_object_record)
        await self._session.flush()
        return StoredFile(file=file, file_object=file_object)

    async def find_by_id(self, *, file_id: UUID) -> StoredFile | None:
        file_record = await self._session.get(orm.File, file_id)
        if file_record is None:
            return None
        return await self._stored_file(file_record=file_record)

    async def find_by_id_for_user(self, *, file_id: UUID, user_id: UUID) -> StoredFile | None:
        statement = select(orm.File).where(
            orm.File.id == file_id,
            orm.File.user_id == user_id,
        )
        file_record = await self._session.scalar(statement)
        if file_record is None:
            return None
        return await self._stored_file(file_record=file_record)

    async def delete_by_id(self, *, file_id: UUID) -> None:
        await self._session.execute(delete(orm.File).where(orm.File.id == file_id))

    async def _stored_file(self, *, file_record: orm.File) -> StoredFile | None:
        statement = (
            select(orm.FileObject)
            .where(orm.FileObject.file_id == file_record.id)
            .order_by(orm.FileObject.created_at)
        )
        file_object_record = await self._session.scalar(statement)
        if file_object_record is None:
            return None
        return mapper.stored_file_to_domain(
            file_record=file_record,
            file_object_record=file_object_record,
        )
