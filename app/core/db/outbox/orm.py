from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (UniqueConstraint("event_id"),)

    id: Mapped[int] = mapped_column(
        type_=BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    event_id: Mapped[UUID] = mapped_column(
        type_=PostgreSQLUUID(as_uuid=True),
        nullable=False,
        default=uuid4,
    )
    event_type: Mapped[str] = mapped_column(type_=String(255), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        type_=JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        default=dict,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        type_=DateTime(timezone=True),
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(
        type_=Integer,
        nullable=False,
        server_default="0",
        default=0,
    )
