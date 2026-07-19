from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.db.session import build_engine
from app.modules.promotions.tests.migration_insert_probes import (
    assert_invalid_promotion_insert_probes,
    assert_signup_context_insert_is_accepted,
)
from app.modules.promotions.tests.migration_promotion_content_table_contract import (
    assert_promotion_content_table_is_constrained,
)
from app.modules.promotions.tests.migration_promotion_nullability_contract import (
    assert_promotion_nullability,
)

EXPECTED_PROMOTION_CHECKS = {
    "ck_promotions_benefit_feature_key_allowed",
    "ck_promotions_context_allowed",
    "ck_promotions_kind_allowed",
    "ck_promotions_benefit_amount_positive",
    "ck_promotions_max_redemptions_positive",
    "ck_promotions_times_redeemed_non_negative",
    "ck_promotions_max_redemptions_per_user_positive",
}
EXPECTED_PROMOTION_CODE_CHECKS = {
    "ck_promotion_codes_max_redemptions_positive",
    "ck_promotion_codes_times_redeemed_non_negative",
}
EXPECTED_PROMOTION_REDEMPTION_CHECKS = {
    "ck_promotion_redemptions_status_allowed",
}


async def assert_promotion_tables_are_constrained(database_url: str) -> list[str]:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            await _assert_table_columns(
                connection,
                "promotions",
                {
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
                    "kind",
                    "benefit_amount",
                    "created_at",
                    "updated_at",
                },
            )
            await _assert_table_columns(
                connection,
                "promotion_codes",
                {
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
                },
            )
            await _assert_table_columns(
                connection,
                "promotion_redemptions",
                {
                    "id",
                    "promotion_id",
                    "promotion_code_id",
                    "user_id",
                    "beneficiary_key",
                    "status",
                    "idempotency_key",
                    "failure_reason",
                    "redeemed_at",
                    "created_at",
                    "updated_at",
                },
            )
            await assert_promotion_content_table_is_constrained(connection)
            await _assert_check_constraint_names(connection)
            await _assert_same_bc_foreign_keys(connection)
            await _assert_unique_indexes(connection)
            await _assert_rewarded_ad_promotion(connection)
            await assert_promotion_nullability(connection)
            await assert_signup_context_insert_is_accepted(connection)
            return await assert_invalid_promotion_insert_probes(connection)
    finally:
        await engine.dispose()


async def _assert_table_columns(
    connection: AsyncConnection,
    table_name: str,
    expected_columns: set[str],
) -> None:
    result = await connection.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    assert {row[0] for row in result.tuples()} == expected_columns


async def _assert_check_constraint_names(connection: AsyncConnection) -> None:
    assert await _check_constraint_names(connection, "promotions") == EXPECTED_PROMOTION_CHECKS
    assert (
        await _check_constraint_names(connection, "promotion_codes")
        == EXPECTED_PROMOTION_CODE_CHECKS
    )
    assert (
        await _check_constraint_names(connection, "promotion_redemptions")
        == EXPECTED_PROMOTION_REDEMPTION_CHECKS
    )


async def _check_constraint_names(
    connection: AsyncConnection,
    table_name: str,
) -> set[str]:
    result = await connection.execute(
        text(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = to_regclass(:qualified_table_name)
              AND contype = 'c'
            """
        ),
        {"qualified_table_name": f"public.{table_name}"},
    )
    return {row[0] for row in result.tuples()}


async def _assert_same_bc_foreign_keys(connection: AsyncConnection) -> None:
    result = await connection.execute(
        text(
            """
            SELECT
                source_table.relname,
                source_column.attname,
                target_table.relname,
                target_column.attname
            FROM pg_constraint AS constraint_info
            JOIN pg_class AS source_table
              ON source_table.oid = constraint_info.conrelid
            JOIN pg_class AS target_table
              ON target_table.oid = constraint_info.confrelid
            JOIN unnest(constraint_info.conkey) WITH ORDINALITY AS source_key(attnum, ordinality)
              ON TRUE
            JOIN unnest(constraint_info.confkey) WITH ORDINALITY AS target_key(attnum, ordinality)
              ON target_key.ordinality = source_key.ordinality
            JOIN pg_attribute AS source_column
              ON source_column.attrelid = source_table.oid
             AND source_column.attnum = source_key.attnum
            JOIN pg_attribute AS target_column
              ON target_column.attrelid = target_table.oid
             AND target_column.attnum = target_key.attnum
            WHERE constraint_info.contype = 'f'
              AND source_table.relname IN (
                  'promotion_codes',
                  'promotion_redemptions'
              )
            ORDER BY source_table.relname, source_column.attname
            """
        )
    )
    assert list(result.tuples()) == [
        ("promotion_codes", "promotion_id", "promotions", "id"),
        ("promotion_redemptions", "promotion_code_id", "promotion_codes", "id"),
        ("promotion_redemptions", "promotion_id", "promotions", "id"),
    ]


async def _assert_unique_indexes(connection: AsyncConnection) -> None:
    result = await connection.execute(
        text(
            """
            SELECT
                index_class.relname,
                index_info.indisunique,
                pg_get_indexdef(index_info.indexrelid)
            FROM pg_index AS index_info
            JOIN pg_class AS table_class
              ON table_class.oid = index_info.indrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            JOIN pg_class AS index_class
              ON index_class.oid = index_info.indexrelid
            WHERE namespace.nspname = 'public'
              AND table_class.relname IN (
                  'promotion_codes',
                  'promotion_redemptions',
                  'promotions'
              )
              AND index_class.relname IN (
                  'ix_promotion_codes_code_unique',
                  'uq_promotion_redemptions_idempotency_key',
                  'uq_promotion_redemptions_promotion_beneficiary',
                  'ix_promotions_current_benefit_context_kind',
                  'uq_promotions_benefit_context_kind_starts_at',
                  'uq_promotions_benefit_context_starts_at_without_kind'
              )
            """
        )
    )
    indexes = {row[0]: (row[1], row[2]) for row in result.tuples()}
    assert indexes == {
        "ix_promotion_codes_code_unique": (
            True,
            "CREATE UNIQUE INDEX ix_promotion_codes_code_unique "
            "ON public.promotion_codes USING btree (lower((code)::text))",
        ),
        "uq_promotion_redemptions_idempotency_key": (
            True,
            "CREATE UNIQUE INDEX uq_promotion_redemptions_idempotency_key "
            "ON public.promotion_redemptions USING btree (idempotency_key)",
        ),
        "uq_promotion_redemptions_promotion_beneficiary": (
            True,
            "CREATE UNIQUE INDEX uq_promotion_redemptions_promotion_beneficiary "
            "ON public.promotion_redemptions USING btree (promotion_id, beneficiary_key) "
            "WHERE (beneficiary_key IS NOT NULL)",
        ),
        "ix_promotions_current_benefit_context_kind": (
            False,
            "CREATE INDEX ix_promotions_current_benefit_context_kind "
            "ON public.promotions USING btree "
            "(benefit_feature_key, context, kind, active, expires_at, starts_at DESC)",
        ),
        "uq_promotions_benefit_context_kind_starts_at": (
            True,
            "CREATE UNIQUE INDEX uq_promotions_benefit_context_kind_starts_at "
            "ON public.promotions USING btree "
            "(benefit_feature_key, context, kind, starts_at) "
            "WHERE ((context IS NOT NULL) AND (kind IS NOT NULL))",
        ),
        "uq_promotions_benefit_context_starts_at_without_kind": (
            True,
            "CREATE UNIQUE INDEX uq_promotions_benefit_context_starts_at_without_kind "
            "ON public.promotions USING btree "
            "(benefit_feature_key, context, starts_at) "
            "WHERE ((context IS NOT NULL) AND (kind IS NULL))",
        ),
    }


async def _assert_rewarded_ad_promotion(connection: AsyncConnection) -> None:
    result = await connection.execute(
        text(
            """
            SELECT
                id::text,
                name,
                active,
                starts_at,
                expires_at,
                max_redemptions,
                times_redeemed,
                max_redemptions_per_user,
                benefit_feature_key,
                context,
                kind,
                benefit_amount
            FROM promotions
            WHERE id = '67a6b0f8-a628-47ae-a2c3-1a5688736829'
            """
        )
    )
    assert result.one() == (
        "67a6b0f8-a628-47ae-a2c3-1a5688736829",
        "광고 시청 OCR 크레딧 충전",
        True,
        datetime(2026, 7, 16, 15, 0, tzinfo=UTC),
        None,
        None,
        0,
        2,
        "ocr",
        "recharge",
        "rewardedAd",
        2,
    )
