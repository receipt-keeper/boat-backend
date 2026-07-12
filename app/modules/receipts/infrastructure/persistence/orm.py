from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.modules.receipts.domain.value_objects import ReceiptCategory

_RECEIPT_CATEGORY_ENUM = SQLAlchemyEnum(
    ReceiptCategory,
    name="receipt_category",
    values_callable=lambda enum_type: [category.value for category in enum_type],
    validate_strings=True,
)


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint(
            "period_months BETWEEN 1 AND 60",
            name="ck_receipts_period_months_range",
        ),
        CheckConstraint(
            "total_amount IS NULL OR total_amount >= 0",
            name="ck_receipts_total_amount_non_negative",
        ),
        Index("ix_receipts_expires_on_id", "expires_on", "id"),
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
    item_name: Mapped[str] = mapped_column(type_=String(255), nullable=False)
    brand_name: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    payment_location: Mapped[str | None] = mapped_column(type_=String(500), nullable=True)
    payment_date: Mapped[date] = mapped_column(type_=Date, nullable=False)
    total_amount: Mapped[int | None] = mapped_column(type_=BigInteger, nullable=True)
    period_months: Mapped[int] = mapped_column(
        type_=Integer,
        nullable=False,
        default=12,
        server_default="12",
    )
    expires_on: Mapped[date] = mapped_column(type_=Date, nullable=False)
    category: Mapped[ReceiptCategory | None] = mapped_column(
        type_=_RECEIPT_CATEGORY_ENUM,
        nullable=True,
    )
    sub_category: Mapped[str | None] = mapped_column(type_=String(100), nullable=True)
    memo: Mapped[str | None] = mapped_column(type_=String(1000), nullable=True)
    requires_physical_receipt: Mapped[bool] = mapped_column(
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


class ReceiptAttachment(Base):
    __tablename__ = "receipt_attachments"
    __table_args__ = (
        UniqueConstraint(
            "receipt_id",
            "file_id",
            name="uq_receipt_attachments_receipt_id_file_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    receipt_id: Mapped[UUID] = mapped_column(
        ForeignKey("receipts.id", ondelete="CASCADE"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    file_id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
