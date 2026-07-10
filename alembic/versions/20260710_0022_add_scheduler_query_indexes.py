from collections.abc import Sequence

from alembic import op

revision: str = "20260710_0022"
down_revision: str | Sequence[str] | None = "20260709_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_users_created_at_id", "users", ["created_at", "id"])
    op.create_index("ix_receipts_expires_on_id", "receipts", ["expires_on", "id"])


def downgrade() -> None:
    op.drop_index("ix_receipts_expires_on_id", table_name="receipts")
    op.drop_index("ix_users_created_at_id", table_name="users")
