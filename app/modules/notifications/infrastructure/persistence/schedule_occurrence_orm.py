from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.core.db.base import Base


class NotificationScheduleOccurrence(Base):
    __tablename__ = "notification_schedule_occurrences"
    __table_args__ = (
        CheckConstraint(
            "campaign_key <> '' AND campaign_key = btrim(campaign_key)",
            name=conv("ck_notification_schedule_occurrences_campaign_key"),
        ),
        CheckConstraint(
            "target_type IN ('receipt', 'user')",
            name=conv("ck_notification_schedule_occurrences_target_type"),
        ),
    )

    campaign_key: Mapped[str] = mapped_column(type_=String(100), primary_key=True)
    target_type: Mapped[str] = mapped_column(type_=String(30), primary_key=True)
    target_id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    occurrence_on: Mapped[date] = mapped_column(type_=Date, primary_key=True)
    notification_id: Mapped[UUID | None] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
