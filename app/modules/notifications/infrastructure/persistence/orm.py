from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.core.db.base import Base


class UserNotification(Base):
    __tablename__ = "user_notifications"
    __table_args__ = (
        Index(
            "ix_user_notifications_user_id_created_at_id",
            "user_id",
            "created_at",
            "id",
        ),
        CheckConstraint(
            "category IN ('service', 'marketing')",
            name=conv("ck_user_notifications_category_allowed"),
        ),
        CheckConstraint(
            "(resource_type IS NULL) = (resource_id IS NULL)",
            name=conv("ck_user_notifications_resource_pair"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(type_=String(20), nullable=False)
    kind: Mapped[str] = mapped_column(type_=String(50), nullable=False)
    title: Mapped[str] = mapped_column(type_=String(100), nullable=False)
    message: Mapped[str] = mapped_column(type_=String(255), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(type_=String(50), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    read_at: Mapped[datetime | None] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=True,
    )


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    user_id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    push_enabled: Mapped[bool] = mapped_column(
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
    __table_args__ = (UniqueConstraint("fid"),)

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    fid: Mapped[str] = mapped_column(type_=String(255), nullable=False)
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
