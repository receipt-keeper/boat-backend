from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Table, UniqueConstraint

from app.modules.promotions.domain.model import PromotionContext
from app.modules.promotions.infrastructure.persistence import mapper, orm

EXPECTED_PROMOTION_CHECKS = {
    "ck_promotions_benefit_feature_key_allowed": "benefit_feature_key IN ('ocr')",
    "ck_promotions_context_allowed": "context IS NULL OR context IN ('recharge')",
    "ck_promotions_benefit_amount_positive": "benefit_amount > 0",
    "ck_promotions_max_redemptions_positive": ("max_redemptions IS NULL OR max_redemptions > 0"),
    "ck_promotions_times_redeemed_non_negative": "times_redeemed >= 0",
    "ck_promotions_max_redemptions_per_user_positive": "max_redemptions_per_user > 0",
}
EXPECTED_PROMOTION_CODE_CHECKS = {
    "ck_promotion_codes_max_redemptions_positive": (
        "max_redemptions IS NULL OR max_redemptions > 0"
    ),
    "ck_promotion_codes_times_redeemed_non_negative": "times_redeemed >= 0",
}
EXPECTED_REDEMPTION_CHECKS = {
    "ck_promotion_redemptions_status_allowed": "status IN ('granted', 'rejected', 'failed')",
}


def test_promotion_orm_declares_exact_tables_and_columns() -> None:
    # Given: Promotion persistence ORM metadata가 로드된다.
    promotion_metadata = orm.Promotion.metadata

    # When: Promotion BC 테이블을 확인한다.
    tables = promotion_metadata.tables

    # Then: T1 승인 테이블만 Promotion persistence surface에 추가된다.
    assert {
        "promotions",
        "promotion_codes",
        "promotion_redemptions",
        "promotion_contents",
    } <= set(tables)
    assert "credit_grants" not in tables
    assert "credit_accounts" not in tables
    assert set(tables["promotions"].c.keys()) == {
        "id",
        "name",
        "active",
        "starts_at",
        "expires_at",
        "max_redemptions",
        "times_redeemed",
        "max_redemptions_per_user",
        "benefit_feature_key",
        "context",
        "benefit_amount",
        "created_at",
        "updated_at",
    }
    assert tables["promotions"].c.context.nullable is True
    assert set(tables["promotion_codes"].c.keys()) == {
        "id",
        "promotion_id",
        "code",
        "active",
        "starts_at",
        "expires_at",
        "max_redemptions",
        "times_redeemed",
        "created_at",
        "updated_at",
    }
    assert set(tables["promotion_redemptions"].c.keys()) == {
        "id",
        "promotion_id",
        "promotion_code_id",
        "user_id",
        "status",
        "idempotency_key",
        "failure_reason",
        "redeemed_at",
        "created_at",
        "updated_at",
    }
    assert set(tables["promotion_contents"].c.keys()) == {
        "id",
        "promotion_id",
        "banner_image_url",
        "created_at",
        "updated_at",
    }
    assert "banner_image_file_id" not in tables["promotion_contents"].c
    assert "image_url" not in tables["promotion_contents"].c


def test_promotion_orm_declares_constraints_and_unique_guards() -> None:
    # Given: Promotion persistence ORM tables가 있다.
    promotions = orm.Promotion.metadata.tables["promotions"]
    promotion_codes = orm.Promotion.metadata.tables["promotion_codes"]
    redemptions = orm.Promotion.metadata.tables["promotion_redemptions"]
    promotion_contents = orm.Promotion.metadata.tables["promotion_contents"]

    # When: check/unique/index constraints를 읽는다.
    promotion_checks = _check_constraints(promotions)
    promotion_indexes = {
        None if index.name is None else str(index.name): index for index in promotions.indexes
    }
    code_checks = _check_constraints(promotion_codes)
    redemption_checks = _check_constraints(redemptions)
    code_indexes = {
        None if index.name is None else str(index.name): index for index in promotion_codes.indexes
    }
    redemption_uniques = {
        constraint.name
        for constraint in redemptions.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    content_uniques = {
        constraint.name
        for constraint in promotion_contents.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    # Then: DB가 benefit/status/count/idempotency/code 중복 계약을 강제한다.
    assert promotion_checks == EXPECTED_PROMOTION_CHECKS
    assert tuple(
        column.name for column in promotion_indexes["ix_promotions_current_benefit_context"].columns
    ) == (
        "benefit_feature_key",
        "context",
        "active",
        "expires_at",
        "starts_at",
    )
    unique_business_key = promotion_indexes["uq_promotions_benefit_context_starts_at"]
    assert unique_business_key.unique is True
    assert tuple(column.name for column in unique_business_key.columns) == (
        "benefit_feature_key",
        "context",
        "starts_at",
    )
    assert str(unique_business_key.dialect_options["postgresql"]["where"]) == (
        "promotions.context IS NOT NULL"
    )
    assert code_checks == EXPECTED_PROMOTION_CODE_CHECKS
    assert redemption_checks == EXPECTED_REDEMPTION_CHECKS
    assert code_indexes["ix_promotion_codes_code_unique"].unique is True
    assert str(code_indexes["ix_promotion_codes_code_unique"].expressions[0]) == (
        "lower(promotion_codes.code)"
    )
    assert redemption_uniques == {
        "uq_promotion_redemptions_idempotency_key",
    }
    assert content_uniques == {"uq_promotion_contents_promotion_id"}
    assert promotion_contents.c.banner_image_url.nullable is True


def test_promotion_orm_declares_only_same_bc_foreign_keys() -> None:
    # Given: Promotion persistence ORM tables가 있다.
    promotion_codes = orm.Promotion.metadata.tables["promotion_codes"]
    redemptions = orm.Promotion.metadata.tables["promotion_redemptions"]
    promotion_contents = orm.Promotion.metadata.tables["promotion_contents"]

    # When: FK surface를 확인한다.
    foreign_keys = {
        (
            constraint.table.name,
            tuple(column.name for column in constraint.columns),
            constraint.referred_table.name,
        )
        for table in (promotion_codes, redemptions, promotion_contents)
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }

    # Then: promotions 내부 FK만 존재하고 user/file 계열은 value reference로 남는다.
    assert foreign_keys == {
        ("promotion_codes", ("promotion_id",), "promotions"),
        ("promotion_contents", ("promotion_id",), "promotions"),
        ("promotion_redemptions", ("promotion_id",), "promotions"),
        ("promotion_redemptions", ("promotion_code_id",), "promotion_codes"),
    }
    assert not redemptions.c.user_id.foreign_keys
    assert not promotion_contents.c.banner_image_url.foreign_keys
    assert redemptions.c.promotion_code_id.nullable is True


def test_promotion_mapper_round_trips_recharge_context() -> None:
    # Given: DB에서 읽은 recharge context promotion row가 있다.
    record = orm.Promotion(
        id=UUID("00000000-0000-0000-0000-000000000901"),
        name="월간 OCR 크레딧 충전",
        active=True,
        starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        expires_at=None,
        max_redemptions=None,
        times_redeemed=0,
        max_redemptions_per_user=1,
        benefit_feature_key="ocr",
        context="recharge",
        benefit_amount=5,
    )

    # When: persistence mapper로 domain entity를 복원한다.
    promotion = mapper.promotion_to_domain(record)

    # Then: context 값이 domain enum으로 보존된다.
    assert promotion.context == PromotionContext.RECHARGE


def test_promotion_mapper_preserves_legacy_null_context() -> None:
    # Given: legacy/code-entered promotion row에는 context가 없다.
    record = orm.Promotion(
        id=UUID("00000000-0000-0000-0000-000000000902"),
        name="일반 OCR 크레딧 프로모션",
        active=True,
        starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        expires_at=None,
        max_redemptions=None,
        times_redeemed=0,
        max_redemptions_per_user=1,
        benefit_feature_key="ocr",
        context=None,
        benefit_amount=3,
    )

    # When: persistence mapper로 domain entity를 복원한다.
    promotion = mapper.promotion_to_domain(record)

    # Then: nullable context 계약이 유지된다.
    assert promotion.context is None


def _check_constraints(table: Table) -> dict[str | None, str]:
    return {
        None if constraint.name is None else str(constraint.name): str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
