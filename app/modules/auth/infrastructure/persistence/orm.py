from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class UserCredential(Base):
    __tablename__ = "user_credentials"

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
        unique=True,
    )
    role: Mapped[str] = mapped_column(
        type_=String(50),
        nullable=False,
        default="user",
        server_default="user",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ExternalIdentity(Base):
    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint("issuer", "subject"),
        UniqueConstraint("credentials_id", "issuer"),
    )

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    credentials_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    issuer: Mapped[str] = mapped_column(type_=String(50), nullable=False)
    subject: Mapped[str] = mapped_column(type_=String(255), nullable=False)
    provider: Mapped[str] = mapped_column(type_=String(50), nullable=False)
    email: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(
        type_=Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    credentials_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    credentials_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_credentials.id", ondelete="CASCADE"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    token_hash: Mapped[str] = mapped_column(type_=String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(type_=DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
