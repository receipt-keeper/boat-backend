from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "ix_users_normalized_email_unique",
            "normalized_email",
            unique=True,
            postgresql_where=text("normalized_email IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(type_=String(2048), nullable=True)
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


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    notification_enabled: Mapped[bool] = mapped_column(
        type_=Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    marketing_consent: Mapped[bool] = mapped_column(
        type_=Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    terms_version: Mapped[str | None] = mapped_column(type_=String(50), nullable=True)
    privacy_version: Mapped[str | None] = mapped_column(type_=String(50), nullable=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=True,
    )
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=True,
    )
    marketing_consent_updated_at: Mapped[datetime | None] = mapped_column(
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


class UserEntitlement(Base):
    __tablename__ = "user_entitlements"
    __table_args__ = (
        CheckConstraint(
            "free_analysis_tokens_remaining >= 0",
            name="ck_user_entitlements_free_analysis_tokens_remaining",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    free_analysis_tokens_remaining: Mapped[int] = mapped_column(
        type_=Integer,
        nullable=False,
        default=0,
        server_default="0",
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


class UserPushToken(Base):
    __tablename__ = "user_push_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id"),
        UniqueConstraint("fcm_token"),
    )

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    device_id: Mapped[str] = mapped_column(type_=String(255), nullable=False)
    fcm_token: Mapped[str] = mapped_column(type_=String(512), nullable=False)
    platform: Mapped[str] = mapped_column(type_=String(50), nullable=False)
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
