from hashlib import blake2b
from typing import Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.ports.external_identity_login_synchronizer import (
    ExternalIdentityLoginSynchronizer,
)
from app.modules.auth.domain.model import ExternalIdentity

_LOCK_KEY_SEPARATOR: Final = "\x1f"
_SIGNED_64_BIT_BYTES: Final = 8


class SqlAlchemyExternalIdentityLoginSynchronizer(ExternalIdentityLoginSynchronizer):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def synchronize(self, *, identity: ExternalIdentity) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _lock_id_for(identity)},
        )


def _lock_id_for(identity: ExternalIdentity) -> int:
    key = _LOCK_KEY_SEPARATOR.join((identity.issuer.value, identity.subject.value))
    digest = blake2b(key.encode("utf-8"), digest_size=_SIGNED_64_BIT_BYTES).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)
