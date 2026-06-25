from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SetProfileImageCommand:
    user_id: UUID
    file_id: UUID


@dataclass(frozen=True, slots=True)
class ClearProfileImageCommand:
    user_id: UUID
