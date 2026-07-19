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
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.core.db.base import Base


class Promotion(Base):
    __tablename__ = "promotions"
    __table_args__ = (
        CheckConstraint(
            "benefit_feature_key IN ('ocr')",
            name=conv("ck_promotions_benefit_feature_key_allowed"),
        ),
        CheckConstraint(
            "context IS NULL OR context IN ('recharge', 'signup')",
            name=conv("ck_promotions_context_allowed"),
        ),
        CheckConstraint(
            "kind IS NULL OR kind IN ('monthlyAllowance', 'rewardedAd')",
            name=conv("ck_promotions_kind_allowed"),
        ),
        CheckConstraint(
            "benefit_amount > 0",
            name=conv("ck_promotions_benefit_amount_positive"),
        ),
        CheckConstraint(
            "max_redemptions IS NULL OR max_redemptions > 0",
            name=conv("ck_promotions_max_redemptions_positive"),
        ),
        CheckConstraint(
            "times_redeemed >= 0",
            name=conv("ck_promotions_times_redeemed_non_negative"),
        ),
        CheckConstraint(
            "max_redemptions_per_user > 0",
            name=conv("ck_promotions_max_redemptions_per_user_positive"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(type_=String(255), nullable=False)
    active: Mapped[bool] = mapped_column(
        type_=Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    starts_at: Mapped[datetime] = mapped_column(type_=DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=True,
    )
    max_redemptions: Mapped[int | None] = mapped_column(type_=Integer, nullable=True)
    times_redeemed: Mapped[int] = mapped_column(
        type_=Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    max_redemptions_per_user: Mapped[int] = mapped_column(
        type_=Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    benefit_feature_key: Mapped[str] = mapped_column(type_=String(50), nullable=False)
    context: Mapped[str | None] = mapped_column(type_=String(50), nullable=True)
    kind: Mapped[str | None] = mapped_column(type_=String(50), nullable=True)
    benefit_amount: Mapped[int] = mapped_column(type_=Integer, nullable=False)
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


Index(
    "ix_promotions_current_benefit_context_kind",
    Promotion.benefit_feature_key,
    Promotion.context,
    Promotion.kind,
    Promotion.active,
    Promotion.expires_at,
    Promotion.starts_at.desc(),
)
Index(
    "uq_promotions_benefit_context_kind_starts_at",
    Promotion.benefit_feature_key,
    Promotion.context,
    Promotion.kind,
    Promotion.starts_at,
    unique=True,
    postgresql_where=Promotion.context.is_not(None) & Promotion.kind.is_not(None),
)
Index(
    "uq_promotions_benefit_context_starts_at_without_kind",
    Promotion.benefit_feature_key,
    Promotion.context,
    Promotion.starts_at,
    unique=True,
    postgresql_where=Promotion.context.is_not(None) & Promotion.kind.is_(None),
)


class PromotionContent(Base):
    __tablename__ = "promotion_contents"
    __table_args__ = (
        UniqueConstraint(
            "promotion_id",
            name=conv("uq_promotion_contents_promotion_id"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    promotion_id: Mapped[UUID] = mapped_column(
        ForeignKey("promotions.id"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    banner_image_url: Mapped[str | None] = mapped_column(type_=String(2048), nullable=True)
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


class PromotionCode(Base):
    __tablename__ = "promotion_codes"
    __table_args__ = (
        CheckConstraint(
            "max_redemptions IS NULL OR max_redemptions > 0",
            name=conv("ck_promotion_codes_max_redemptions_positive"),
        ),
        CheckConstraint(
            "times_redeemed >= 0",
            name=conv("ck_promotion_codes_times_redeemed_non_negative"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    promotion_id: Mapped[UUID] = mapped_column(
        ForeignKey("promotions.id"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(type_=String(100), nullable=False)
    active: Mapped[bool] = mapped_column(
        type_=Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    starts_at: Mapped[datetime | None] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=True,
    )
    max_redemptions: Mapped[int | None] = mapped_column(type_=Integer, nullable=True)
    times_redeemed: Mapped[int] = mapped_column(
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


Index("ix_promotion_codes_code_unique", func.lower(PromotionCode.code), unique=True)


class PromotionRedemption(Base):
    __tablename__ = "promotion_redemptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('granted', 'rejected', 'failed')",
            name=conv("ck_promotion_redemptions_status_allowed"),
        ),
        UniqueConstraint(
            "idempotency_key",
            name=conv("uq_promotion_redemptions_idempotency_key"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    promotion_id: Mapped[UUID] = mapped_column(
        ForeignKey("promotions.id"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    promotion_code_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("promotion_codes.id"),
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    user_id: Mapped[UUID] = mapped_column(type_=PostgreSQLUUID(as_uuid=True), nullable=False)
    beneficiary_key: Mapped[str | None] = mapped_column(type_=String(80), nullable=True)
    status: Mapped[str] = mapped_column(type_=String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(type_=String(255), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(type_=String(255), nullable=True)
    redeemed_at: Mapped[datetime | None] = mapped_column(
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


Index(
    "uq_promotion_redemptions_promotion_beneficiary",
    PromotionRedemption.promotion_id,
    PromotionRedemption.beneficiary_key,
    unique=True,
    postgresql_where=PromotionRedemption.beneficiary_key.is_not(None),
)
