from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def assert_promotion_nullability(connection: AsyncConnection) -> None:
    result = await connection.execute(
        text(
            """
            SELECT table_name, column_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND (
                  (table_name = 'promotion_codes' AND column_name IN ('starts_at', 'expires_at'))
                  OR (table_name = 'promotions' AND column_name = 'context')
                  OR (
                      table_name = 'promotion_redemptions'
                      AND column_name IN ('promotion_code_id', 'beneficiary_key')
                  )
              )
            """
        )
    )
    nullable = {(row[0], row[1]): row[2] for row in result.tuples()}
    assert nullable == {
        ("promotion_codes", "starts_at"): "YES",
        ("promotion_codes", "expires_at"): "YES",
        ("promotions", "context"): "YES",
        ("promotion_redemptions", "beneficiary_key"): "YES",
        ("promotion_redemptions", "promotion_code_id"): "YES",
    }
