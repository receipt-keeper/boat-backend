from dataclasses import dataclass
from uuid import UUID

from app.core.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class UserCredentialCreated(DomainEvent):
    credentials_id: UUID
    user_id: UUID
    role: str


@dataclass(frozen=True, kw_only=True)
class AccountWithdrawn(DomainEvent):
    credentials_id: UUID
    user_id: UUID
