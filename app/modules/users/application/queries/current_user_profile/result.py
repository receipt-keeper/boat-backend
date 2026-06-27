from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CurrentUserProfileResult:
    user_id: UUID
    email: str | None
    name: str | None
    nickname: str | None
    profile_image_url: str | None
