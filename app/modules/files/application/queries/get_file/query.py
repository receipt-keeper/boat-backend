from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GetFileQuery:
    file_id: UUID
    user_id: UUID
