from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ResolveUserForLoginResult:
    user_id: UUID
    notification_enabled: bool
    marketing_consent: bool
    free_analysis_tokens_remaining: int
