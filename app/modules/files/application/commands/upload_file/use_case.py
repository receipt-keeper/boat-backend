from uuid import UUID, uuid4

from app.core.application.unit_of_work import DeferredCommitUnitOfWork, UnitOfWork
from app.modules.files.application.commands.upload_file.command import UploadFileCommand
from app.modules.files.application.commands.upload_file.result import UploadFileResult
from app.modules.files.application.ports.file_repository import FileRepository
from app.modules.files.application.ports.object_storage import ObjectStorage
from app.modules.files.domain.model import File, FileObject


class UploadFileCommandUseCase:
    def __init__(
        self,
        repository: FileRepository,
        storage: ObjectStorage | None = None,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._unit_of_work = unit_of_work or DeferredCommitUnitOfWork()

    async def execute(self, command: UploadFileCommand) -> UploadFileResult:
        file_id = uuid4()
        storage_key = command.storage_key or _build_storage_key(
            user_id=command.user_id,
            file_id=file_id,
        )
        file = File.create(
            file_id=file_id,
            user_id=command.user_id,
            original_name=command.original_name,
            purpose=command.purpose,
        )
        file_object = FileObject.create(
            file_id=file.id,
            storage_key=storage_key,
            content_type=command.content_type,
            size=command.size,
            checksum=command.checksum,
        )
        if self._storage is not None:
            stored_object = await self._storage.put(
                key=file_object.storage_key.value,
                content=command.content,
            )
            file_object = FileObject.create(
                file_id=file.id,
                storage_backend=stored_object.storage_backend,
                storage_key=stored_object.storage_key,
                content_type=command.content_type,
                size=stored_object.size,
                checksum=stored_object.checksum,
            )
        stored_file = await self._repository.save(file=file, file_object=file_object)
        await self._unit_of_work.commit()
        return UploadFileResult(
            file_id=stored_file.file.id,
            original_name=stored_file.file.original_name.value,
            content_type=stored_file.file_object.content_type.value,
            size=stored_file.file_object.size.value,
            content_path=f"/files/{stored_file.file.id}/content",
        )


def _build_storage_key(*, user_id: UUID, file_id: UUID) -> str:
    return f"users/{user_id}/files/{file_id}/original"
