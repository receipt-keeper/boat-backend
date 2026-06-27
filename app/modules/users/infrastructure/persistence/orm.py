from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
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
