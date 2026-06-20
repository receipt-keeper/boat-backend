from dataclasses import dataclass


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
