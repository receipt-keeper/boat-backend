from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DeleteFileCommand:
    file_id: UUID
    user_id: UUID
