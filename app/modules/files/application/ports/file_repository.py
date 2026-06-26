from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.files.domain.model import File, FileObject, StoredFile


class FileRepository(ABC):
    @abstractmethod
    async def save(self, *, file: File, file_object: FileObject) -> StoredFile:
        raise NotImplementedError

    @abstractmethod
    async def find_by_id(self, *, file_id: UUID) -> StoredFile | None:
        raise NotImplementedError

    @abstractmethod
    async def find_by_id_for_user(self, *, file_id: UUID, user_id: UUID) -> StoredFile | None:
        raise NotImplementedError

    @abstractmethod
    async def find_all_by_id_for_user(
        self,
        *,
        file_id: UUID,
        user_id: UUID,
    ) -> tuple[StoredFile, ...]:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_id(self, *, file_id: UUID) -> None:
        raise NotImplementedError
