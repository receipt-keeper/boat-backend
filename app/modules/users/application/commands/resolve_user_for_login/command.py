from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolveUserForLoginCommand:
    name: str | None
    email: str | None
    profile_image_url: str | None
    terms_version: str | None = None
    privacy_version: str | None = None
    terms_accepted: bool = False
    privacy_accepted: bool = False
