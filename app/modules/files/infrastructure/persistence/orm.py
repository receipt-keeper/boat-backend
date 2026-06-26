from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class File(Base):
    __tablename__ = "files"
    __table_args__ = (Index("ix_files_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(type_=PostgreSQLUUID(as_uuid=True), nullable=False)
    original_name: Mapped[str] = mapped_column(type_=String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FileObject(Base):
    __tablename__ = "file_objects"
    __table_args__ = (
        UniqueConstraint("storage_key"),
        Index("ix_file_objects_file_id_variant_type", "file_id", "variant_type", unique=True),
    )

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    variant_type: Mapped[str] = mapped_column(type_=String(50), nullable=False)
    storage_key: Mapped[str] = mapped_column(type_=String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(type_=String(100), nullable=False)
    size: Mapped[int] = mapped_column(type_=BigInteger, nullable=False)
    checksum: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
