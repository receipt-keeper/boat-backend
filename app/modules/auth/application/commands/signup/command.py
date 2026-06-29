from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignupCommand:
    provider_token: str
    terms_accepted: bool
    privacy_accepted: bool
    terms_version: str | None
    privacy_version: str | None
    marketing_consent: bool = False
