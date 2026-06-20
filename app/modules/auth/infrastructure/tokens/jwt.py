from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from app.core.config.settings import Settings
from app.modules.auth.application.constants import AUTHENTICATION_FAILED_MESSAGE
from app.modules.auth.application.ports.token_issuer import (
    AccessTokenIssuer,
    AccessTokenVerifier,
    IssuedAccessToken,
)
from app.modules.auth.application.principal import AuthenticatedPrincipal
from app.modules.auth.domain.exceptions import AuthenticationError

JWT_ALGORITHM_HS256 = "HS256"
JWT_CLAIM_ISSUER = "iss"
JWT_CLAIM_AUDIENCE = "aud"
JWT_CLAIM_SUBJECT = "sub"
JWT_CLAIM_CREDENTIALS_ID = "credentials_id"
JWT_CLAIM_SESSION_ID = "sid"
JWT_CLAIM_ROLE = "role"
JWT_CLAIM_ISSUED_AT = "iat"
JWT_CLAIM_EXPIRES_AT = "exp"
JWT_CLAIM_ID = "jti"
REQUIRED_ACCESS_TOKEN_CLAIMS = (
    JWT_CLAIM_ISSUER,
    JWT_CLAIM_AUDIENCE,
    JWT_CLAIM_SUBJECT,
    JWT_CLAIM_CREDENTIALS_ID,
    JWT_CLAIM_SESSION_ID,
    JWT_CLAIM_ROLE,
    JWT_CLAIM_ISSUED_AT,
    JWT_CLAIM_EXPIRES_AT,
    JWT_CLAIM_ID,
)


class JwtAccessTokenService(AccessTokenIssuer, AccessTokenVerifier):
    def __init__(
        self,
        *,
        secret_key: str,
        issuer: str,
        audience: str,
        expires_minutes: int,
        algorithm: str = JWT_ALGORITHM_HS256,
    ) -> None:
        self._secret_key = secret_key
        self._issuer = issuer
        self._audience = audience
        self._expires_minutes = expires_minutes
        self._algorithm = algorithm

    @classmethod
    def from_settings(cls, settings: Settings) -> "JwtAccessTokenService":
        return cls(
            secret_key=settings.jwt_secret_key,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            expires_minutes=settings.access_token_expires_minutes,
            algorithm=settings.jwt_algorithm,
        )

    def issue(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
        session_id: UUID,
        role: str,
    ) -> IssuedAccessToken:
        issued_at = datetime.now(UTC)
        expires_at = issued_at + timedelta(minutes=self._expires_minutes)
        expires_in = int((expires_at - issued_at).total_seconds())
        claims = {
            JWT_CLAIM_ISSUER: self._issuer,
            JWT_CLAIM_AUDIENCE: self._audience,
            JWT_CLAIM_SUBJECT: str(user_id),
            JWT_CLAIM_CREDENTIALS_ID: str(credentials_id),
            JWT_CLAIM_SESSION_ID: str(session_id),
            JWT_CLAIM_ROLE: role,
            JWT_CLAIM_ISSUED_AT: issued_at,
            JWT_CLAIM_EXPIRES_AT: expires_at,
            JWT_CLAIM_ID: str(uuid4()),
        }

        token = jwt.encode(claims, self._secret_key, algorithm=self._algorithm)
        return IssuedAccessToken(token=token, expires_at=expires_at, expires_in=expires_in)

    def verify(self, token: str) -> AuthenticatedPrincipal:
        try:
            claims = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": list(REQUIRED_ACCESS_TOKEN_CLAIMS),
                },
            )
            return AuthenticatedPrincipal(
                user_id=UUID(str(claims[JWT_CLAIM_SUBJECT])),
                credentials_id=UUID(str(claims[JWT_CLAIM_CREDENTIALS_ID])),
                session_id=UUID(str(claims[JWT_CLAIM_SESSION_ID])),
                role=str(claims[JWT_CLAIM_ROLE]),
            )
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE) from exc
