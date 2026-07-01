from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GetUsageSnapshotQuery:
    user_id: UUID
