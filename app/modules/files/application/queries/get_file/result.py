from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GetFileResult:
    file_id: UUID
    original_name: str
    purpose: str
    status: str
    content_type: str
    size: int
    content_path: str
