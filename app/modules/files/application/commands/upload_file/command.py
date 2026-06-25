from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UploadFileCommand:
    user_id: UUID
    original_name: str
    content_type: str
    size: int
    content: bytes = b""
    purpose: str = "profile_image"
    storage_key: str | None = None
    checksum: str | None = None
