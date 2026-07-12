from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.core.db.base import Base


class UserCredit(Base):
    __tablename__ = "user_credits"
    __table_args__ = (
        CheckConstraint(
            "feature_key IN ('ocr')",
            name=conv("ck_user_credits_feature_key_allowed"),
        ),
        CheckConstraint(
            "total_granted_count >= 0",
            name=conv("ck_user_credits_total_granted_count_non_negative"),
        ),
        CheckConstraint(
            "used_count >= 0",
            name=conv("ck_user_credits_used_count_non_negative"),
        ),
        CheckConstraint(
            "remaining_count >= 0",
            name=conv("ck_user_credits_remaining_count_non_negative"),
        ),
        CheckConstraint(
            "total_granted_count = used_count + remaining_count",
            name=conv("ck_user_credits_counts_consistent"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    feature_key: Mapped[str] = mapped_column(
        type_=String(50),
        primary_key=True,
    )
    current_period: Mapped[str | None] = mapped_column(type_=String(7), nullable=True)
    total_granted_count: Mapped[int] = mapped_column(
        type_=Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    used_count: Mapped[int] = mapped_column(
        type_=Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    remaining_count: Mapped[int] = mapped_column(
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


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    __table_args__ = (
        CheckConstraint(
            "feature_key IN ('ocr')",
            name=conv("ck_credit_transactions_feature_key_allowed"),
        ),
        CheckConstraint(
            "reason IN ('monthlyOcrAllowance', 'eventOcrAllowance', 'ocrUsage')",
            name=conv("ck_credit_transactions_reason_allowed"),
        ),
        CheckConstraint(
            "action IN ('grant', 'use')",
            name=conv("ck_credit_transactions_action_allowed"),
        ),
        CheckConstraint(
            "(reason IN ('monthlyOcrAllowance', 'eventOcrAllowance') AND action = 'grant') "
            "OR (reason = 'ocrUsage' AND action = 'use')",
            name=conv("ck_credit_transactions_reason_action_pair"),
        ),
        CheckConstraint(
            "amount > 0",
            name=conv("ck_credit_transactions_amount_positive"),
        ),
        CheckConstraint(
            "source_type IS NULL "
            "OR source_type IN ('promotionRedemption', 'monthlyAllowance', 'ocrAnalysis')",
            name=conv("ck_credit_transactions_source_type_allowed"),
        ),
        CheckConstraint(
            "(source_type IS NULL AND source_id IS NULL) "
            "OR (source_type IS NOT NULL AND source_id IS NOT NULL)",
            name=conv("ck_credit_transactions_source_pair_complete"),
        ),
        Index(
            "ix_credit_transactions_user_id_feature_key_created_at_id",
            "user_id",
            "feature_key",
            "created_at",
            "id",
        ),
        Index(
            "ix_credit_transactions_idempotency_key_unique",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_credit_transactions_source_unique",
            "source_type",
            "source_id",
            "user_id",
            "feature_key",
            "action",
            unique=True,
            postgresql_where=text("source_type IS NOT NULL AND source_id IS NOT NULL"),
        ),
        Index(
            "ix_credit_transactions_purge_after",
            "purge_after",
            postgresql_where=text("purge_after IS NOT NULL"),
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
    )
    feature_key: Mapped[str] = mapped_column(type_=String(50), nullable=False)
    reason: Mapped[str] = mapped_column(type_=String(50), nullable=False)
    action: Mapped[str] = mapped_column(type_=String(20), nullable=False)
    amount: Mapped[int] = mapped_column(type_=Integer, nullable=False)
    source_type: Mapped[str | None] = mapped_column(type_=String(50), nullable=True)
    source_id: Mapped[UUID | None] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    purge_after: Mapped[datetime | None] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
