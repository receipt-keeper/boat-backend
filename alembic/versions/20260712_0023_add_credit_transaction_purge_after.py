"""add credit transaction purge_after

Revision ID: 20260712_0023
Revises: 20260710_0022
Create Date: 2026-07-12 00:23:00.000000

가입 보너스 claim(credit_transactions의 signup-allowance idempotency row)의 보존 상태를
관리하기 위해 purge_after: timestamptz | None 컬럼을 추가한다. NULL이면 만료 없음(활성 claim)
이고, 값이 있으면 그 시각 이후 백그라운드 파기 대상이다. partial index는 파기 폴러의 만료 row
조회를 지원한다.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260712_0023"
down_revision: str | Sequence[str] | None = "20260710_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "credit_transactions",
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_credit_transactions_purge_after",
        "credit_transactions",
        ["purge_after"],
        postgresql_where=sa.text("purge_after IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_credit_transactions_purge_after", table_name="credit_transactions")
    op.drop_column("credit_transactions", "purge_after")
