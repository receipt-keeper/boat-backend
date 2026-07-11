from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.ports.withdrawn_identity import WithdrawnIdentityRegistry
from app.modules.auth.infrastructure.persistence import orm


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyWithdrawnIdentityRegistry(WithdrawnIdentityRegistry):
    def __init__(
        self,
        session: AsyncSession,
        *,
        retention_days: int,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session = session
        self._retention_days = retention_days
        self._clock = clock

    async def mark_withdrawn(self, *, identity_hashes: Sequence[str]) -> None:
        if not identity_hashes:
            return

        now = self._clock()
        expires_at = now + timedelta(days=self._retention_days)
        insert_statement = postgresql_insert(orm.WithdrawnIdentity).values(
            [
                {
                    "identity_hash": identity_hash,
                    "withdrawn_at": now,
                    "expires_at": expires_at,
                }
                for identity_hash in identity_hashes
            ]
        )
        await self._session.execute(
            insert_statement.on_conflict_do_update(
                index_elements=[orm.WithdrawnIdentity.identity_hash],
                set_={
                    "withdrawn_at": insert_statement.excluded.withdrawn_at,
                    "expires_at": insert_statement.excluded.expires_at,
                },
            )
        )

    async def exists(self, *, identity_hash: str) -> bool:
        statement = select(orm.WithdrawnIdentity.identity_hash).where(
            orm.WithdrawnIdentity.identity_hash == identity_hash,
            orm.WithdrawnIdentity.expires_at > self._clock(),
        )
        return await self._session.scalar(statement) is not None
