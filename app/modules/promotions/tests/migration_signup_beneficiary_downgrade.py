from sqlalchemy import text

from app.core.db.session import build_engine


async def insert_signup_promotion_and_redemption(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO promotions (
                        id, name, active, starts_at, benefit_feature_key, context, benefit_amount
                    )
                    VALUES (
                        '00000000-0000-0000-0000-000000000601',
                        'signup downgrade target', true, now(), 'ocr', 'signup', 10
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO promotion_redemptions (
                        id, promotion_id, user_id, beneficiary_key, status, idempotency_key
                    )
                    VALUES (
                        '00000000-0000-0000-0000-000000000602',
                        '00000000-0000-0000-0000-000000000601',
                        '00000000-0000-0000-0000-000000000603',
                        'signup:stable-subject', 'granted', 'signup-downgrade-target'
                    )
                    """
                )
            )
    finally:
        await engine.dispose()


async def read_signup_data(database_url: str) -> tuple[str | None, bool, int, bool]:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            context = await connection.scalar(
                text(
                    "SELECT context FROM promotions "
                    "WHERE id = '00000000-0000-0000-0000-000000000601'"
                )
            )
            active = await connection.scalar(
                text(
                    "SELECT active FROM promotions "
                    "WHERE id = '00000000-0000-0000-0000-000000000601'"
                )
            )
            redemptions = await connection.scalar(
                text(
                    "SELECT count(*) FROM promotion_redemptions "
                    "WHERE id = '00000000-0000-0000-0000-000000000602'"
                )
            )
            beneficiary_column = await connection.scalar(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND table_name = 'promotion_redemptions' "
                    "AND column_name = 'beneficiary_key'"
                    ")"
                )
            )
            assert isinstance(context, str | None)
            assert isinstance(active, bool)
            assert isinstance(redemptions, int)
            assert isinstance(beneficiary_column, bool)
            return context, active, redemptions, beneficiary_column
    finally:
        await engine.dispose()
