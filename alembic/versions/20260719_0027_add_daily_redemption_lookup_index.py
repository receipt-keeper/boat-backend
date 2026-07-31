from collections.abc import Sequence

from alembic import op

revision: str = "20260719_0027"
down_revision: str | Sequence[str] | None = "20260719_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_promotion_redemptions_user_promotion_status_redeemed_at",
        "promotion_redemptions",
        ["user_id", "promotion_id", "status", "redeemed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_promotion_redemptions_user_promotion_status_redeemed_at",
        table_name="promotion_redemptions",
    )
