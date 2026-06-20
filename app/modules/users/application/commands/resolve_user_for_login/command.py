from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolveUserForLoginCommand:
    name: str | None
    email: str
    profile_image_url: str | None
    initial_free_analysis_tokens: int = 0
    terms_version: str | None = None
    privacy_version: str | None = None
    terms_accepted: bool = False
    privacy_accepted: bool = False
    marketing_consent: bool = False
