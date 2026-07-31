"""영수증 무상 AS 기간 범위를 확장한다.

Revision ID: 20260731_0026
Revises: 20260717_0025

운영 배포는 migration을 실행한 뒤 blue/green 슬롯을 전환하므로 schema 변경은 이전
백엔드와도 호환되어야 한다. 구매가격 상한은 API·도메인에서 먼저 적용하고, DB 상한은
이전 이미지의 롤백 기간이 끝난 뒤 별도 migration으로 강화한다.

다운그레이드는 60개월 초과 데이터가 있으면 이전 기간 제약을 복원할 수 없으므로
명시적으로 중단한다.
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
    op.create_check_constraint(
        op.f("ck_receipts_period_months_range"),
        "receipts",
        "period_months BETWEEN 1 AND 120",
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
        op.f("ck_receipts_period_months_range"),
        "receipts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_receipts_period_months_range"),
        "receipts",
        "period_months BETWEEN 1 AND 60",
    )
