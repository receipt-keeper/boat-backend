"""rename user push tokens fid to token

Revision ID: 20260705_0014
Revises: 20260705_0013
Create Date: 2026-07-05 00:14:00.000000

FID(Firebase Installation ID) 발송은 클라이언트가 firebase-messaging 25.1.0+의 신규
등록 경로(비래퍼 경로)로 전환해야 동작하는데, 앱의 SMP 래퍼가 이 경로를 막는다는 것이
실측으로 확정됐다. 반면 FCM registration token 발송은 deprecated 상태지만 여전히
동작하고 제거 공지가 없으므로, 디바이스 식별자를 FID에서 token으로 되돌린다.

`user_push_tokens`의 기존 행은 전부 FID 값이라 token 기반 발송에 그대로 쓸 수 없는
죽은 데이터다. token 값은 FID로부터 유도할 수 없으므로(클라이언트가 `getToken()`으로
새로 발급받아 재등록해야 함) 컬럼 rename 전에 전량 삭제한다.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260705_0014"
down_revision: str | Sequence[str] | None = "20260705_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 기존 행은 전부 FID 값이라 token 발송에 사용할 수 없는 죽은 데이터다. rename 전에
    # 전량 삭제해 죽은 FID 값이 token 컬럼으로 그대로 넘어가지 않도록 한다.
    op.execute("DELETE FROM user_push_tokens")

    op.drop_constraint(
        op.f("uq_user_push_tokens_fid"),
        "user_push_tokens",
        type_="unique",
    )
    op.alter_column(
        "user_push_tokens",
        "fid",
        new_column_name="token",
        existing_type=sa.String(length=255),
        type_=sa.String(length=512),
        existing_nullable=False,
    )
    op.create_unique_constraint(
        op.f("uq_user_push_tokens_token"),
        "user_push_tokens",
        ["token"],
    )


def downgrade() -> None:
    # token 값은 FID로 환원할 수 없으므로(발급 알고리즘이 다르고 원본 FID를 보존하지
    # 않음) 컬럼을 원래 형태로 되돌리기 전에 전량 삭제하는 것이 안전하다.
    op.execute("DELETE FROM user_push_tokens")

    op.drop_constraint(
        op.f("uq_user_push_tokens_token"),
        "user_push_tokens",
        type_="unique",
    )
    op.alter_column(
        "user_push_tokens",
        "token",
        new_column_name="fid",
        existing_type=sa.String(length=512),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.create_unique_constraint(
        op.f("uq_user_push_tokens_fid"),
        "user_push_tokens",
        ["fid"],
    )
