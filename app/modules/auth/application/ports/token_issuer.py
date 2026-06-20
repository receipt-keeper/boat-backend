from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.auth.application.principal import AuthenticatedPrincipal


@dataclass(frozen=True)
class IssuedAccessToken:
    token: str
    expires_at: datetime
    expires_in: int


@dataclass(frozen=True)
class IssuedRefreshToken:
    token: str
    token_hash: str
    expires_at: datetime


class AccessTokenIssuer(ABC):
    @abstractmethod
    def issue(self, *, user_id: UUID, credentials_id: UUID, role: str) -> IssuedAccessToken:
        raise NotImplementedError


class AccessTokenVerifier(ABC):
    @abstractmethod
    def verify(self, token: str) -> AuthenticatedPrincipal:
        raise NotImplementedError


class RefreshTokenIssuer(ABC):
    @abstractmethod
    def issue(self) -> IssuedRefreshToken:
        raise NotImplementedError


class RefreshTokenHasher(ABC):
    @abstractmethod
    def hash(self, token: str) -> str:
        raise NotImplementedError
