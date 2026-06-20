from dataclasses import dataclass


@dataclass(frozen=True)
class LoginCommand:
    provider_token: str
    terms_version: str | None = None
    privacy_version: str | None = None
    terms_accepted: bool = False
    privacy_accepted: bool = False
    marketing_consent: bool = False
