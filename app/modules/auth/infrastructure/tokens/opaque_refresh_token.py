import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.modules.auth.application.ports.token_issuer import (
    IssuedRefreshToken,
    RefreshTokenHasher,
    RefreshTokenIssuer,
)

REFRESH_TOKEN_BYTES = 48
REFRESH_TOKEN_HASH_SEPARATOR = b":"


class OpaqueRefreshTokenIssuer(RefreshTokenIssuer, RefreshTokenHasher):
    def __init__(self, *, pepper: str, expires_days: int) -> None:
        self._pepper = pepper
        self._expires_days = expires_days

    def issue(self) -> IssuedRefreshToken:
        token = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
        return IssuedRefreshToken(
            token=token,
            token_hash=self.hash(token),
            expires_at=datetime.now(UTC) + timedelta(days=self._expires_days),
        )

    def hash(self, token: str) -> str:
        digest = hashlib.sha256()
        digest.update(self._pepper.encode())
        digest.update(REFRESH_TOKEN_HASH_SEPARATOR)
        digest.update(token.encode())
        return digest.hexdigest()
