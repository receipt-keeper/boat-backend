from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config.settings import Settings
from app.main import create_app
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.tokens.jwt import JwtAccessTokenService
from app.modules.users.application.ports.user_repository import CreateUserAccountState
from app.modules.users.domain.model import User, UserSettings
from app.modules.users.infrastructure.persistence.repository import SqlAlchemyUserRepository

IMAGE_BYTES = b"\x89PNG\r\n\x1a\nprofile-image"


@dataclass(frozen=True, slots=True)
class SeededUser:
    user_id: UUID
    credentials_id: UUID
    access_token: str


async def seed_user(
    session: AsyncSession,
    *,
    subject: str,
    email: str,
    name: str,
    settings: Settings,
) -> SeededUser:
    user = User.create(name=name, email=email)
    await SqlAlchemyUserRepository(session).create_account_state(
        state=CreateUserAccountState(
            user=user,
            settings=UserSettings.create(user_id=user.id),
        )
    )
    credentials = await SqlAlchemyCredentialRepository(session).create_for_external_identity(
        identity=ExternalIdentity.create(
            issuer="google",
            subject=subject,
            provider="google",
            email=email,
            name=name,
        ),
        user_id=user.id,
        logged_in_at=datetime.now(UTC),
    )
    session_id = credentials.credentials_id
    session.add(
        auth_orm.AuthSession(
            id=session_id,
            credentials_id=credentials.credentials_id,
        )
    )
    access_token = JwtAccessTokenService.from_settings(settings).issue(
        user_id=user.id,
        credentials_id=credentials.credentials_id,
        session_id=session_id,
        role=credentials.role.value,
    )
    return SeededUser(
        user_id=user.id,
        credentials_id=credentials.credentials_id,
        access_token=access_token.token,
    )


@asynccontextmanager
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> AsyncIterator[AsyncClient]:
    test_app = create_app(settings)
    test_app.state.session_factory = session_factory
    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


def make_test_settings(
    storage_root: Path,
    *,
    max_upload_bytes: int = 10_485_760,
    api_prefix: str = "/api/v1",
) -> Settings:
    return Settings(
        api_prefix=api_prefix,
        jwt_secret_key="x" * 48,
        jwt_issuer="boat-backend-test",
        jwt_audience="boat-api-test",
        file_storage_root=str(storage_root),
        file_max_upload_bytes=max_upload_bytes,
    )


def auth_headers(seeded: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {seeded.access_token}"}


def stored_local_files(storage_root: Path) -> list[Path]:
    if not storage_root.exists():
        return []
    return [path for path in storage_root.rglob("*") if path.is_file()]
