from datetime import datetime, time

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.core.db.base import Base


class NotificationScheduleRule(Base):
    __tablename__ = "notification_schedule_rules"
    __table_args__ = (
        CheckConstraint(
            "campaign_key <> '' AND campaign_key = btrim(campaign_key)",
            name=conv("ck_notification_schedule_rules_campaign_key"),
        ),
        CheckConstraint(
            "target_kind IN ("
            "'warranty_receipt', "
            "'engagement_unregistered_receipt', "
            "'engagement_inactive_receipt', "
            "'engagement_all_user')",
            name=conv("ck_notification_schedule_rules_target_kind"),
        ),
        CheckConstraint(
            "day_offset IS NULL OR day_offset >= 0",
            name=conv("ck_notification_schedule_rules_day_offset"),
        ),
        CheckConstraint(
            "first_delay_days IS NULL OR first_delay_days >= 0",
            name=conv("ck_notification_schedule_rules_first_delay_days"),
        ),
        CheckConstraint(
            "repeat_interval_days IS NULL OR repeat_interval_days >= 0",
            name=conv("ck_notification_schedule_rules_repeat_interval_days"),
        ),
        CheckConstraint(
            "lookback_days IS NULL OR lookback_days >= 0",
            name=conv("ck_notification_schedule_rules_lookback_days"),
        ),
        CheckConstraint(
            "target_kind <> 'warranty_receipt' OR "
            "(day_offset IS NOT NULL AND first_delay_days IS NULL "
            "AND repeat_interval_days IS NULL AND lookback_days IS NULL)",
            name=conv("ck_notification_schedule_rules_warranty_timing"),
        ),
        CheckConstraint(
            "target_kind = 'warranty_receipt' OR repeat_interval_days IS NOT NULL",
            name=conv("ck_notification_schedule_rules_engagement_timing"),
        ),
        CheckConstraint(
            "target_kind = 'warranty_receipt' OR requires_marketing_consent",
            name=conv("ck_notification_schedule_rules_engagement_consent"),
        ),
    )

    campaign_key: Mapped[str] = mapped_column(type_=String(100), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        type_=Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    target_kind: Mapped[str] = mapped_column(type_=String(50), nullable=False)
    day_offset: Mapped[int | None] = mapped_column(type_=Integer, nullable=True)
    first_delay_days: Mapped[int | None] = mapped_column(type_=Integer, nullable=True)
    repeat_interval_days: Mapped[int | None] = mapped_column(type_=Integer, nullable=True)
    lookback_days: Mapped[int | None] = mapped_column(type_=Integer, nullable=True)
    send_time_local: Mapped[time] = mapped_column(type_=Time(timezone=False), nullable=False)
    requires_marketing_consent: Mapped[bool] = mapped_column(
        type_=Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    title_template: Mapped[str] = mapped_column(type_=String(100), nullable=False)
    body_template: Mapped[str] = mapped_column(type_=String(255), nullable=False)
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
