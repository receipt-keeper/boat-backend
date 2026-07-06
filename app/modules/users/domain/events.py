from dataclasses import dataclass
from uuid import UUID

from app.core.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class UserRegistered(DomainEvent):
    user_id: UUID
    email: str | None
    name: str | None


@dataclass(frozen=True, kw_only=True)
class UserProfileImageChanged(DomainEvent):
    user_id: UUID
    previous_image_url: str | None
    new_image_url: str | None


@dataclass(frozen=True, kw_only=True)
class UserWithdrawn(DomainEvent):
    user_id: UUID
