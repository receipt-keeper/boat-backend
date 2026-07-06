from dataclasses import dataclass
from uuid import UUID

from app.core.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class FileUploaded(DomainEvent):
    file_id: UUID
    user_id: UUID
    original_name: str
    content_type: str
    size: int
    storage_key: str


@dataclass(frozen=True, kw_only=True)
class FileDeleted(DomainEvent):
    file_id: UUID
    user_id: UUID
    storage_keys: list[str]
