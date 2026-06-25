from uuid import UUID

from app.core.domain.exceptions import NotFoundError


class FileNotFoundError(NotFoundError):
    def __init__(self, *, file_id: UUID) -> None:
        self.file_id = file_id
        super().__init__("파일을 찾을 수 없습니다.")
