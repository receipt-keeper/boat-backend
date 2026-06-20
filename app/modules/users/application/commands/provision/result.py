from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ProvisionUserResult:
    user_id: UUID
