from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UploadFileResult:
    file_id: UUID
    original_name: str
    content_type: str
    size: int
    content_path: str
