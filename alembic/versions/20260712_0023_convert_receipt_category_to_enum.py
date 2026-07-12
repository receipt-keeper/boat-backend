"""convert receipt category to enum

Revision ID: 20260712_0023
Revises: 20260710_0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260712_0023"
down_revision: str | Sequence[str] | None = "20260710_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORY_VALUES = (
    "kitchen_appliance",
    "laundry_cleaning",
    "living_climate",
    "it_device",
    "other_device",
)
_RECEIPT_CATEGORY_ENUM = postgresql.ENUM(
    *_CATEGORY_VALUES,
    name="receipt_category",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _RECEIPT_CATEGORY_ENUM.create(bind, checkfirst=True)
    op.execute(
        sa.text(
            """
            UPDATE receipts
            SET category = CASE
                WHEN lower(regexp_replace(category, '[[:space:]]+', '', 'g'))
                    IN ('kitchen_appliance', '주방가전')
                    THEN 'kitchen_appliance'
                WHEN lower(regexp_replace(category, '[[:space:]]+', '', 'g'))
                    IN ('laundry_cleaning', '세탁/청소', '세탁청소')
                    THEN 'laundry_cleaning'
                WHEN lower(regexp_replace(category, '[[:space:]]+', '', 'g'))
                    IN ('living_climate', '리빙/냉난방', '리빙냉난방')
                    THEN 'living_climate'
                WHEN lower(regexp_replace(category, '[[:space:]]+', '', 'g'))
                    IN ('it_device', 'it기기', 'it제품', '영상/it제품', '영상it제품')
                    OR lower(regexp_replace(category, '[[:space:]]+', '', 'g')) LIKE 'it%'
                    THEN 'it_device'
                WHEN lower(regexp_replace(category, '[[:space:]]+', '', 'g'))
                    IN ('other_device', '기타기기', '기타제품', '기타')
                    THEN 'other_device'
                ELSE 'other_device'
            END
            WHERE category IS NOT NULL
            """
        )
    )
    op.alter_column(
        "receipts",
        "category",
        existing_type=sa.String(length=100),
        type_=_RECEIPT_CATEGORY_ENUM,
        existing_nullable=True,
        postgresql_using="category::receipt_category",
    )


def downgrade() -> None:
    op.alter_column(
        "receipts",
        "category",
        existing_type=_RECEIPT_CATEGORY_ENUM,
        type_=sa.String(length=100),
        existing_nullable=True,
        postgresql_using="category::text",
    )
    _RECEIPT_CATEGORY_ENUM.drop(op.get_bind(), checkfirst=True)
