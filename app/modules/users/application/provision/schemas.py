from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ProvisionUserCommand:
    name: str | None
    email: str | None


@dataclass(frozen=True)
class ProvisionUserResult:
    user_id: UUID
