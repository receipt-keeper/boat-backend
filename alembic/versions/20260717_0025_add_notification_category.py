from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260717_0025"
down_revision: str | Sequence[str] | None = "20260712_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_notifications",
        sa.Column(
            "category",
            sa.String(length=50),
            nullable=True,
            server_default=sa.text("'product_management'"),
        ),
    )
    op.execute(
        sa.text(
            "UPDATE user_notifications "
            "SET category = CASE "
            "WHEN kind = 'warranty' OR kind LIKE 'warranty_%' THEN 'warranty' "
            "WHEN kind IN ("
            "'benefit', 'credit_prompt', 'receipt_analysis_reminder', 'engagement_all_user'"
            ") "
            "THEN 'benefit' "
            "ELSE 'product_management' END"
        )
    )
    op.create_check_constraint(
        op.f("ck_user_notifications_category_allowed"),
        "user_notifications",
        "category IN ('product_management', 'warranty', 'benefit')",
    )
    op.alter_column(
        "user_notifications",
        "category",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default=sa.text("'product_management'"),
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_user_notifications_category_allowed"),
        "user_notifications",
        type_="check",
    )
    op.drop_column("user_notifications", "category")
