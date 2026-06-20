from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.core.domain.entity import Entity
from app.core.domain.validation import Notification
from app.modules.auth.domain.value_objects import Issuer, Provider, Role, Subject, TokenHash


@dataclass(eq=False)
class UserCredential(Entity[UUID]):
    user_id: UUID
    role: Role
    last_login_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        role: str = "user",
        credentials_id: UUID | None = None,
        last_login_at: datetime | None = None,
    ) -> "UserCredential":
        new_role = Role(role)
        return cls(
            id=credentials_id or uuid4(),
            user_id=user_id,
            role=new_role,
            last_login_at=last_login_at,
        )

    @property
    def credentials_id(self) -> UUID:
        return self.id


@dataclass(eq=False)
class ExternalIdentity(Entity[UUID]):
    issuer: Issuer
    subject: Subject
    provider: Provider
    email: str | None
    name: str | None
    credentials_id: UUID | None = None

    @classmethod
    def create(
        cls,
        *,
        issuer: str,
        subject: str,
        provider: str,
        email: str | None,
        name: str | None,
        identity_id: UUID | None = None,
        credentials_id: UUID | None = None,
    ) -> "ExternalIdentity":
        notification = Notification()
        new_issuer = notification.collect(lambda: Issuer(issuer))
        new_subject = notification.collect(lambda: Subject(subject))
        new_provider = notification.collect(lambda: Provider(provider))
        notification.raise_if_any()

        return cls(
            id=identity_id or uuid4(),
            credentials_id=credentials_id,
            issuer=new_issuer,
            subject=new_subject,
            provider=new_provider,
            email=email,
            name=name,
        )


@dataclass(eq=False)
class RefreshToken(Entity[UUID]):
    credentials_id: UUID
    token_hash: TokenHash
    expires_at: datetime

    @classmethod
    def create(
        cls,
        *,
        credentials_id: UUID,
        token_hash: str,
        expires_at: datetime,
        refresh_token_id: UUID | None = None,
    ) -> "RefreshToken":
        return cls(
            id=refresh_token_id or uuid4(),
            credentials_id=credentials_id,
            token_hash=TokenHash(token_hash),
            expires_at=expires_at,
        )
