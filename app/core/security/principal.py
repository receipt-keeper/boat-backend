from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: UUID
    credentials_id: UUID
    session_id: UUID
    role: str
