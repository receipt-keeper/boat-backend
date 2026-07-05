from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def assert_promotion_content_table_is_constrained(
    connection: AsyncConnection,
) -> None:
    await _assert_content_columns(connection)
    await _assert_content_foreign_keys(connection)
    await _assert_content_unique_index(connection)
    await _assert_content_nullable_columns(connection)


async def _assert_content_columns(connection: AsyncConnection) -> None:
    result = await connection.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'promotion_contents'
            """
        )
    )
    assert {row[0] for row in result.tuples()} == {
        "id",
        "promotion_id",
        "banner_image_url",
        "created_at",
        "updated_at",
    }


async def _assert_content_foreign_keys(connection: AsyncConnection) -> None:
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
              AND source_table.relname = 'promotion_contents'
            ORDER BY source_table.relname, source_column.attname
            """
        )
    )
    assert list(result.tuples()) == [
        ("promotion_contents", "promotion_id", "promotions", "id"),
    ]


async def _assert_content_unique_index(connection: AsyncConnection) -> None:
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
              AND table_class.relname = 'promotion_contents'
              AND index_class.relname = 'uq_promotion_contents_promotion_id'
            """
        )
    )
    indexes = {row[0]: (row[1], row[2]) for row in result.tuples()}
    assert indexes == {
        "uq_promotion_contents_promotion_id": (
            True,
            "CREATE UNIQUE INDEX uq_promotion_contents_promotion_id "
            "ON public.promotion_contents USING btree (promotion_id)",
        ),
    }


async def _assert_content_nullable_columns(connection: AsyncConnection) -> None:
    result = await connection.execute(
        text(
            """
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'promotion_contents'
              AND column_name = 'banner_image_url'
            """
        )
    )
    assert {row[0]: row[1] for row in result.tuples()} == {"banner_image_url": "YES"}
