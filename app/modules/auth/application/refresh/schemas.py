from dataclasses import dataclass


@dataclass(frozen=True)
class RefreshTokenCommand:
    refresh_token: str


@dataclass(frozen=True)
class RefreshTokenResult:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
