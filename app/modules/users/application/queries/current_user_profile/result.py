from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CurrentUserProfileResult:
    user_id: UUID
    email: str | None
    normalized_email: str | None
    name: str | None
    nickname: str | None
    profile_image_url: str | None
    notification_enabled: bool
    marketing_consent: bool
    free_analysis_tokens_remaining: int
    push_token_count: int
