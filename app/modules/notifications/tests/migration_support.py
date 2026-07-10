from pathlib import Path

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

PROJECT_ROOT = Path(__file__).parents[4]


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("prepend_sys_path", str(PROJECT_ROOT))
    config.set_main_option("path_separator", "os")
    return config


async def table_column_names(
    connection: AsyncConnection,
    table_name: str,
) -> set[str]:
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
    return {row[0] for row in result.tuples()}
