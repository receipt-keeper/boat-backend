"""create outbox events

Revision ID: 20260705_0015
Revises: 20260705_0014
Create Date: 2026-07-05 00:15:00.000000

트랜잭셔널 아웃박스 테이블을 생성한다. 도메인 이벤트는 원 트랜잭션과 같은 세션에서
이 테이블에 insert되고(commit 전), 커밋 후 즉시 발행 경로 또는 폴러가 읽어 발행한 뒤
삭제한다. 상태 컬럼은 두지 않는다(발행 완료 row는 즉시 delete).

Retry 선별은 occurred_at + retry_count 조합으로 이뤄지므로 두 컬럼 모두 인덱스가 없어도
되지만, 폴러의 `ORDER BY id LIMIT ... FOR UPDATE SKIP LOCKED` 질의는 기본 PK 순서 스캔으로
충분하다(운영 스케일은 Scope OUT).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260705_0015"
down_revision: str | Sequence[str] | None = "20260705_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
        sa.UniqueConstraint("event_id", name=op.f("uq_outbox_events_event_id")),
    )


def downgrade() -> None:
    op.drop_table("outbox_events")
