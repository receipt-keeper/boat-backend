"""create withdrawn identities

Revision ID: 20260712_0023
Revises: 20260710_0022
Create Date: 2026-07-12 00:23:00.000000

탈퇴한 external identity의 HMAC 해시만 기간 한정 보존하는 tombstone 테이블을 생성한다.
user_id·이메일·원본 subject 등 재식별 가능한 컬럼은 두지 않는다. `expires_at` 인덱스는
백그라운드 파기 폴러의 만료 row 조회를 지원한다.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260712_0023"
down_revision: str | Sequence[str] | None = "20260710_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "withdrawn_identities",
        sa.Column("identity_hash", sa.String(length=64), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("identity_hash", name=op.f("pk_withdrawn_identities")),
    )
    op.create_index(
        "ix_withdrawn_identities_expires_at",
        "withdrawn_identities",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_withdrawn_identities_expires_at", table_name="withdrawn_identities")
    op.drop_table("withdrawn_identities")
