from dataclasses import dataclass


@dataclass(frozen=True)
class LoginCommand:
    provider_token: str
