from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExistingUserIds:
    user_ids: frozenset[UUID]
