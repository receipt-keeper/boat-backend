"""generalize user notifications

Revision ID: 20260705_0013
Revises: 20260704_0012
Create Date: 2026-07-05 00:13:00.000000

알림 BC가 발신 도메인 어휘(NotificationKind enum, 화면 어휘 target_type)를 모르도록
category(불투명 kind 게이팅용) + title(발신자 완성 문구) + resource_type/resource_id
(불투명 리소스 참조 쌍) + metadata(발신자 소유 부가 정보, JSONB NOT NULL DEFAULT '{}')로
일반화한다.

Backfill 규칙:
- category: 기존 kind='benefit'이면 'marketing', 그 외는 'service'.
- title: 기존 kind별 PUSH_TITLES 매핑(ELSE '알림').
- resource_type/resource_id: 기존 target_type이 'none' 또는 'receiptUpload'이거나
  target_id가 NULL인 행은 쌍을 모두 NULL로 정리한다. 그 외(target_type='receipt'이고
  target_id가 있는 행)는 target_type -> resource_type, target_id -> resource_id로 이전한다.

downgrade는 역순으로 복원한다. 단, 구 리비전 코드는 kind/target_type을 enum으로 읽으므로:
- 'receiptUpload'(등록 유도)와 'none'(대상 없음)의 구분은 resource 쌍 NULL 정리 과정에서
  소실되어 downgrade 시 두 값 모두 'none'으로 복원된다(비가역).
- 구 enum 밖 불투명 resource_type(새 API가 수용한 값)은 '대상 없음'('none')으로
  정규화한다(비가역).
- 구 enum 밖 불투명 kind는 구 코드가 읽을 수 없고 안전한 대체 값도 없으므로 downgrade를
  명시적으로 실패시킨다(해당 행을 정리한 뒤 재시도).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260705_0013"
down_revision: str | Sequence[str] | None = "20260704_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PUSH_TITLE_BY_KIND = {
    "warranty_notice": "보증 기간 안내",
    "warranty_warning": "보증 만료 주의",
    "warranty_risk": "보증 만료 임박",
    "warranty_expired": "보증 만료",
    "registration_prompt": "영수증 등록 안내",
    "credit_prompt": "크레딧 안내",
    "benefit": "혜택 안내",
}

# 구 리비전(20260704_0012 이하) 코드가 enum으로 읽을 수 있는 값 전체.
_LEGACY_KINDS: tuple[str, ...] = tuple(_PUSH_TITLE_BY_KIND)
_LEGACY_TARGET_TYPES: tuple[str, ...] = ("receipt", "receiptUpload", "none")


def upgrade() -> None:
    # 1) category: nullable로 추가 -> backfill -> NOT NULL + CHECK
    op.add_column(
        "user_notifications",
        sa.Column("category", sa.String(length=20), nullable=True),
    )
    op.execute(
        "UPDATE user_notifications SET category = "
        "CASE WHEN kind = 'benefit' THEN 'marketing' ELSE 'service' END"
    )
    op.alter_column("user_notifications", "category", nullable=False)
    op.create_check_constraint(
        op.f("ck_user_notifications_category_allowed"),
        "user_notifications",
        "category IN ('service', 'marketing')",
    )

    # 2) title: nullable로 추가 -> backfill(kind별 매핑, ELSE '알림') -> NOT NULL
    op.add_column(
        "user_notifications",
        sa.Column("title", sa.String(length=100), nullable=True),
    )
    connection = op.get_bind()
    for kind, title in _PUSH_TITLE_BY_KIND.items():
        connection.execute(
            sa.text("UPDATE user_notifications SET title = :title WHERE kind = :kind"),
            {"title": title, "kind": kind},
        )
    connection.execute(sa.text("UPDATE user_notifications SET title = '알림' WHERE title IS NULL"))
    op.alter_column("user_notifications", "title", nullable=False)

    # 3) target_type -> resource_type rename + nullable 전환, 화면 어휘/대상 없음 행은 쌍 정리
    op.alter_column(
        "user_notifications",
        "target_type",
        new_column_name="resource_type",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    op.execute(
        "UPDATE user_notifications SET resource_type = NULL "
        "WHERE resource_type IN ('none', 'receiptUpload') OR target_id IS NULL"
    )

    # 4) target_id -> resource_id rename, resource_type이 정리된(NULL) 행은 id도 NULL로 정리
    op.alter_column(
        "user_notifications",
        "target_id",
        new_column_name="resource_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.execute("UPDATE user_notifications SET resource_id = NULL WHERE resource_type IS NULL")

    # 5) resource 쌍 불변식 CHECK
    op.create_check_constraint(
        op.f("ck_user_notifications_resource_pair"),
        "user_notifications",
        "(resource_type IS NULL) = (resource_id IS NULL)",
    )

    # 6) metadata: 발신자 소유 부가 정보(JSONB), 기본값 '{}' NOT NULL
    op.add_column(
        "user_notifications",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    # 구 리비전 코드는 kind를 NotificationKind enum으로 읽는다. enum 밖 불투명 kind가
    # 남은 채 내리면 rollback 후 목록/조회가 ValueError로 죽고 안전한 대체 값도 없으므로,
    # downgrade를 명시적으로 실패시킨다(해당 행을 정리한 뒤 재시도).
    connection = op.get_bind()
    unknown_kind_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM user_notifications WHERE kind NOT IN :kinds").bindparams(
            sa.bindparam("kinds", expanding=True)
        ),
        {"kinds": list(_LEGACY_KINDS)},
    ).scalar_one()
    if unknown_kind_count:
        raise RuntimeError(
            "user_notifications에 구 NotificationKind enum 밖의 kind 값이 "
            f"{unknown_kind_count}건 남아 있어 downgrade할 수 없습니다. "
            "해당 행을 정리하거나 구 enum 값으로 갱신한 뒤 다시 시도하세요."
        )

    op.drop_column("user_notifications", "metadata")

    op.drop_constraint(
        op.f("ck_user_notifications_resource_pair"),
        "user_notifications",
        type_="check",
    )

    op.alter_column(
        "user_notifications",
        "resource_id",
        new_column_name="target_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # receiptUpload/none 구분은 정리 과정에서 소실되었으므로 전부 'none'으로 복원한다(비가역).
    op.alter_column(
        "user_notifications",
        "resource_type",
        new_column_name="target_type",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    # 구 enum 밖 불투명 resource_type은 구 코드가 읽을 수 없으므로 '대상 없음'으로
    # 정규화한다(비가역). 쌍 불변식에 따라 target_id도 함께 정리한다.
    connection.execute(
        sa.text(
            "UPDATE user_notifications SET target_type = NULL, target_id = NULL "
            "WHERE target_type IS NOT NULL AND target_type NOT IN :types"
        ).bindparams(sa.bindparam("types", expanding=True)),
        {"types": list(_LEGACY_TARGET_TYPES)},
    )
    op.execute("UPDATE user_notifications SET target_type = 'none' WHERE target_type IS NULL")
    op.alter_column("user_notifications", "target_type", nullable=False)

    op.drop_column("user_notifications", "title")

    op.drop_constraint(
        op.f("ck_user_notifications_category_allowed"),
        "user_notifications",
        type_="check",
    )
    op.drop_column("user_notifications", "category")
