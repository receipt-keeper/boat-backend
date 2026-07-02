from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.db.session import build_engine
from app.modules.credits.tests.migration_insert_probes import (
    assert_credit_transaction_insert_probes,
    assert_user_credit_insert_probes,
)

EXPECTED_USER_CREDIT_CHECKS = {
    "ck_user_credits_feature_key_allowed",
    "ck_user_credits_total_granted_count_non_negative",
    "ck_user_credits_used_count_non_negative",
    "ck_user_credits_remaining_count_non_negative",
    "ck_user_credits_counts_consistent",
}
EXPECTED_TRANSACTION_CHECKS = {
    "ck_credit_transactions_feature_key_allowed",
    "ck_credit_transactions_reason_allowed",
    "ck_credit_transactions_action_allowed",
    "ck_credit_transactions_reason_action_pair",
    "ck_credit_transactions_amount_positive",
}


async def assert_credit_tables_are_constrained(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            await _assert_table_exists(connection, "user_credits")
            await _assert_table_exists(connection, "credit_transactions")
            await _assert_table_is_absent(connection, "credit_accounts")
            await _assert_user_id_has_no_foreign_key(connection)
            await _assert_user_credits_primary_key(connection)
            await _assert_transaction_index_exists(connection)
            await _assert_credit_tables_have_no_comments(connection)
            await _assert_check_constraint_names(connection)
            await assert_credit_transaction_insert_probes(connection)
            await assert_user_credit_insert_probes(connection)
    finally:
        await engine.dispose()


async def _assert_table_exists(connection: AsyncConnection, table_name: str) -> None:
    exists = await _table_exists(connection, table_name)
    assert exists is True


async def _assert_table_is_absent(connection: AsyncConnection, table_name: str) -> None:
    exists = await _table_exists(connection, table_name)
    assert exists is False


async def _table_exists(connection: AsyncConnection, table_name: str) -> bool:
    result = await connection.scalar(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    )
    return result is True


async def _assert_user_id_has_no_foreign_key(connection: AsyncConnection) -> None:
    user_id_foreign_keys = await connection.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.table_constraints AS constraints
            JOIN information_schema.key_column_usage AS key_usage
              ON constraints.constraint_name = key_usage.constraint_name
             AND constraints.table_schema = key_usage.table_schema
            WHERE constraints.constraint_type = 'FOREIGN KEY'
              AND constraints.table_schema = 'public'
              AND constraints.table_name IN ('user_credits', 'credit_transactions')
              AND key_usage.column_name = 'user_id'
            """
        )
    )
    assert user_id_foreign_keys == 0


async def _assert_user_credits_primary_key(connection: AsyncConnection) -> None:
    primary_key_columns = await connection.execute(
        text(
            """
            SELECT key_usage.column_name
            FROM information_schema.table_constraints AS constraints
            JOIN information_schema.key_column_usage AS key_usage
              ON constraints.constraint_name = key_usage.constraint_name
             AND constraints.table_schema = key_usage.table_schema
            WHERE constraints.constraint_type = 'PRIMARY KEY'
              AND constraints.table_schema = 'public'
              AND constraints.table_name = 'user_credits'
            ORDER BY key_usage.ordinal_position
            """
        )
    )
    assert [row[0] for row in primary_key_columns.tuples()] == [
        "user_id",
        "feature_key",
    ]


async def _assert_transaction_index_exists(connection: AsyncConnection) -> None:
    index_rows = await connection.execute(
        text(
            """
            SELECT index_class.relname, array_agg(attribute.attname ORDER BY key.ordinality)
            FROM pg_index AS index_info
            JOIN pg_class AS table_class
              ON table_class.oid = index_info.indrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            JOIN pg_class AS index_class
              ON index_class.oid = index_info.indexrelid
            JOIN LATERAL unnest(index_info.indkey) WITH ORDINALITY AS key(attnum, ordinality)
              ON TRUE
            JOIN pg_attribute AS attribute
              ON attribute.attrelid = table_class.oid
             AND attribute.attnum = key.attnum
            WHERE namespace.nspname = 'public'
              AND table_class.relname = 'credit_transactions'
              AND index_info.indisprimary IS FALSE
            GROUP BY index_class.relname
            """
        )
    )
    indexes = {row[0]: tuple(row[1]) for row in index_rows.tuples()}
    assert indexes["ix_credit_transactions_user_id_feature_key_created_at_id"] == (
        "user_id",
        "feature_key",
        "created_at",
        "id",
    )


async def _assert_credit_tables_have_no_comments(connection: AsyncConnection) -> None:
    comment_count = await connection.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM pg_description AS description
            JOIN pg_class AS table_class
              ON table_class.oid = description.objoid
            JOIN pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            WHERE namespace.nspname = 'public'
              AND table_class.relname IN ('user_credits', 'credit_transactions')
              AND (
                  description.objsubid = 0
                  OR description.objsubid IN (
                      SELECT attribute.attnum
                      FROM pg_attribute AS attribute
                      WHERE attribute.attrelid = table_class.oid
                        AND attribute.attnum > 0
                        AND attribute.attisdropped IS FALSE
                  )
              )
            """
        )
    )
    assert comment_count == 0


async def _assert_check_constraint_names(connection: AsyncConnection) -> None:
    user_credit_checks = await _check_constraint_names(connection, "user_credits")
    transaction_checks = await _check_constraint_names(connection, "credit_transactions")

    assert user_credit_checks == EXPECTED_USER_CREDIT_CHECKS, user_credit_checks
    assert transaction_checks == EXPECTED_TRANSACTION_CHECKS, transaction_checks


async def _check_constraint_names(
    connection: AsyncConnection,
    table_name: str,
) -> set[str]:
    constraint_rows = await connection.execute(
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
    return {row[0] for row in constraint_rows.tuples()}
