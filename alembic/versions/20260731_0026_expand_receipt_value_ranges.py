"""영수증 구매가격과 무상 AS 기간 범위를 정합화한다.

Revision ID: 20260731_0026
Revises: 20260717_0025

기존 계약은 구매가격 상한이 없었으므로 운영 DB에 10억 원 이상의 값이 있을 수 있다.
가격 제약은 NOT VALID로 추가해 기존 값을 보존하면서 신규 쓰기부터 제한하고, 기존 위반
데이터가 없을 때만 즉시 검증 완료 상태로 전환한다.

다운그레이드는 60개월 초과 데이터가 있으면 이전 기간 제약을 복원할 수 없으므로
명시적으로 중단한다. 구매가격은 이전 계약에서 상한이 없었으므로 다운그레이드 가드
대상이 아니다.
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
    op.execute(
        """
        ALTER TABLE receipts
        ADD CONSTRAINT ck_receipts_total_amount_range
        CHECK (total_amount IS NULL OR total_amount BETWEEN 0 AND 999999999)
        NOT VALID
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM receipts
                WHERE total_amount > 999999999
            ) THEN
                ALTER TABLE receipts
                VALIDATE CONSTRAINT ck_receipts_total_amount_range;
            END IF;
        END
        $$
        """
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
            ) THEN
                RAISE EXCEPTION
                    'Cannot restore legacy warranty range while out-of-range rows exist';
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
