from dataclasses import dataclass
from uuid import UUID

from app.core.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ExampleUserCreated(DomainEvent):
    example_user_id: UUID
    email: str
