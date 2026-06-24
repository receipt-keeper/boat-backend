from app.modules.files.application.ports.file_repository import FileRepository
from app.modules.files.application.queries.get_file.query import GetFileQuery
from app.modules.files.application.queries.get_file.result import GetFileResult
from app.modules.files.domain.exceptions import FileNotFoundError


class GetFileQueryUseCase:
    def __init__(self, repository: FileRepository) -> None:
        self._repository = repository

    async def execute(self, query: GetFileQuery) -> GetFileResult:
        stored_file = await self._repository.find_by_id_for_user(
            file_id=query.file_id,
            user_id=query.user_id,
        )
        if stored_file is None:
            raise FileNotFoundError(file_id=query.file_id)
        return GetFileResult(
            file_id=stored_file.file.id,
            original_name=stored_file.file.original_name.value,
            purpose=stored_file.file.purpose.value,
            status=stored_file.file.status.value,
            content_type=stored_file.file_object.content_type.value,
            size=stored_file.file_object.size.value,
            content_path=f"/api/v1/files/{stored_file.file.id}/content",
        )
