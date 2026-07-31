"""영수증 구매가격과 무상 AS 기간 범위를 확장한다.

Revision ID: 20260731_0026
Revises: 20260717_0025

다운그레이드는 60개월 초과 또는 999,999,999원 초과 데이터가 있으면
이전 제약조건을 복원할 수 없으므로 명시적으로 중단한다.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260731_0026"
down_revision: str | Sequence[str] | None = "20260717_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_receipts_period_months_range"),
        "receipts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_receipts_total_amount_non_negative"),
        "receipts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_receipts_period_months_range"),
        "receipts",
        "period_months BETWEEN 1 AND 120",
    )
    op.create_check_constraint(
        op.f("ck_receipts_total_amount_range"),
        "receipts",
        "total_amount IS NULL OR total_amount BETWEEN 0 AND 999999999",
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM receipts
                WHERE period_months > 60
                   OR total_amount > 999999999
            ) THEN
                RAISE EXCEPTION
                    'Cannot restore legacy receipt ranges while out-of-range rows exist';
            END IF;
        END
        $$
        """
    )
    op.drop_constraint(
        op.f("ck_receipts_total_amount_range"),
        "receipts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_receipts_period_months_range"),
        "receipts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_receipts_total_amount_non_negative"),
        "receipts",
        "total_amount IS NULL OR total_amount >= 0",
    )
    op.create_check_constraint(
        op.f("ck_receipts_period_months_range"),
        "receipts",
        "period_months BETWEEN 1 AND 60",
    )
