from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.users.application.queries.list_user_registration_facts.query import (
    UserRegistrationFactCursor,
)


@dataclass(frozen=True, slots=True)
class UserRegistrationFact:
    user_id: UUID
    registered_at: datetime


@dataclass(frozen=True, slots=True)
class UserRegistrationFactsPage:
    facts: tuple[UserRegistrationFact, ...]
    next_cursor: UserRegistrationFactCursor | None
