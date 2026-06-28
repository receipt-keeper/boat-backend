from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ListNotificationsQuery:
    user_id: UUID
    cursor: str | None = None
    limit: int = 20
