from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignupResult:
    access_token: str
    refresh_token: str
    expires_in: int
