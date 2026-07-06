from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.core.domain.entity import AggregateRoot, Entity
from app.core.domain.validation import Notification
from app.modules.auth.domain.events import UserCredentialCreated
from app.modules.auth.domain.value_objects import (
    Email,
    Issuer,
    Provider,
    Role,
    Subject,
    TokenHash,
)


@dataclass(eq=False)
class UserCredential(AggregateRoot[UUID]):
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
        created = cls._assemble(
            user_id=user_id,
            role=role,
            credentials_id=credentials_id,
            last_login_at=last_login_at,
        )
        created.record_event(
            UserCredentialCreated(
                credentials_id=created.credentials_id,
                user_id=created.user_id,
                role=created.role.value,
            )
        )
        return created

    @classmethod
    def restore(
        cls,
        *,
        user_id: UUID,
        role: str,
        credentials_id: UUID,
        last_login_at: datetime | None = None,
    ) -> "UserCredential":
        # 저장된 레코드 복원 전용 — 생성 이벤트를 기록하지 않는다.
        return cls._assemble(
            user_id=user_id,
            role=role,
            credentials_id=credentials_id,
            last_login_at=last_login_at,
        )

    @classmethod
    def _assemble(
        cls,
        *,
        user_id: UUID,
        role: str,
        credentials_id: UUID | None,
        last_login_at: datetime | None,
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
    email: Email | None
    email_verified: bool
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
        email_verified: bool = False,
        identity_id: UUID | None = None,
        credentials_id: UUID | None = None,
    ) -> "ExternalIdentity":
        notification = Notification()
        new_issuer = notification.collect(lambda: Issuer(issuer))
        new_subject = notification.collect(lambda: Subject(subject))
        new_provider = notification.collect(lambda: Provider(provider))
        new_email = None if email is None else notification.collect(lambda: Email(email))
        notification.raise_if_any()

        return cls(
            id=identity_id or uuid4(),
            credentials_id=credentials_id,
            issuer=new_issuer,
            subject=new_subject,
            provider=new_provider,
            email=new_email,
            email_verified=email_verified,
            name=name,
        )


@dataclass(eq=False)
class AuthSession(AggregateRoot[UUID]):
    """세션 단위 불변식(리프레시 토큰 로테이션)을 소유하는 구조적 애그리거트 루트.

    UserCredential에 묶으면 고빈도 세션 변경이 credential 애그리거트를 비대하게
    만들어 별도 루트로 분리했다. 세션 수명 이벤트는 소비자가 없어 발행하지 않는다.
    """

    credentials_id: UUID
    revoked_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        credentials_id: UUID,
        session_id: UUID | None = None,
        revoked_at: datetime | None = None,
    ) -> "AuthSession":
        return cls(
            id=session_id or uuid4(),
            credentials_id=credentials_id,
            revoked_at=revoked_at,
        )

    @property
    def session_id(self) -> UUID:
        return self.id


@dataclass(eq=False)
class RefreshToken(Entity[UUID]):
    credentials_id: UUID
    token_hash: TokenHash
    expires_at: datetime
    session_id: UUID | None = None

    @classmethod
    def create(
        cls,
        *,
        credentials_id: UUID,
        token_hash: str,
        expires_at: datetime,
        session_id: UUID | None = None,
        refresh_token_id: UUID | None = None,
    ) -> "RefreshToken":
        return cls(
            id=refresh_token_id or uuid4(),
            credentials_id=credentials_id,
            token_hash=TokenHash(token_hash),
            expires_at=expires_at,
            session_id=session_id,
        )
