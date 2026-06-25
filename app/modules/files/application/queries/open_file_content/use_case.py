from app.modules.files.application.ports.file_repository import FileRepository
from app.modules.files.application.ports.object_storage import ObjectStorage
from app.modules.files.application.queries.open_file_content.query import OpenFileContentQuery
from app.modules.files.application.queries.open_file_content.result import OpenFileContentResult
from app.modules.files.domain.exceptions import FileNotFoundError


class OpenFileContentQueryUseCase:
    def __init__(self, repository: FileRepository, storage: ObjectStorage) -> None:
        self._repository = repository
        self._storage = storage

    async def execute(self, query: OpenFileContentQuery) -> OpenFileContentResult:
        stored_file = await self._repository.find_by_id_for_user(
            file_id=query.file_id,
            user_id=query.user_id,
        )
        if stored_file is None:
            raise FileNotFoundError(file_id=query.file_id)
        content = await self._storage.read(key=stored_file.file_object.storage_key.value)
        return OpenFileContentResult(
            content=content,
            content_type=stored_file.file_object.content_type.value,
            size=stored_file.file_object.size.value,
        )
