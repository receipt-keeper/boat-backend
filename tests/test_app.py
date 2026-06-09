from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient

from app.core.config.settings import Settings
from app.core.http.exceptions import AppError
from app.main import app, create_app
from app.modules.examples.dependencies import get_example_user_service
from app.modules.examples.domain.example_user import ExampleUser


class InMemoryExampleUserService:
    def __init__(self) -> None:
        self._users: dict[UUID, ExampleUser] = {}

    async def get_example_user(self, example_user_id: UUID) -> ExampleUser:
        example_user = self._users.get(example_user_id)
        if example_user is None:
            raise AppError("예시 사용자를 찾을 수 없습니다.", status_code=404)

        return example_user

    async def create_example_user(self, *, nickname: str, email: str) -> ExampleUser:
        example_user = ExampleUser(
            id=uuid4(),
            nickname=nickname,
            email=email,
        )
        self._users[example_user.id] = example_user
        return example_user


async def test_health_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_example_user_endpoints_use_success_envelope() -> None:
    service = InMemoryExampleUserService()
    app.dependency_overrides[get_example_user_service] = lambda: service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        try:
            create_response = await client.post(
                "/api/v1/examples",
                json={
                    "nickname": "created-user",
                    "email": "created@test.com",
                    "password": "password123",
                },
            )

            created_body = create_response.json()
            created_id = created_body["data"]["id"]
            get_response = await client.get(f"/api/v1/examples/{created_id}")
        finally:
            app.dependency_overrides.clear()

    assert create_response.status_code == 201
    assert created_body == {
        "success": True,
        "status": 201,
        "data": {
            "id": created_id,
            "nickname": "created-user",
            "email": "created@test.com",
        },
    }

    assert get_response.status_code == 200
    assert get_response.json() == {
        "success": True,
        "status": 200,
        "data": {
            "id": created_id,
            "nickname": "created-user",
            "email": "created@test.com",
        },
    }


async def test_validation_error_uses_failure_envelope() -> None:
    service = InMemoryExampleUserService()
    app.dependency_overrides[get_example_user_service] = lambda: service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        try:
            response = await client.post(
                "/api/v1/examples",
                json={
                    "nickname": "test-user",
                    "email": "invalid",
                    "password": "short",
                },
            )
        finally:
            app.dependency_overrides.clear()

    body = response.json()

    assert response.status_code == 400
    assert body["success"] is False
    assert body["status"] == 400
    assert body["data"]["message"] == "잘못된 요청입니다."
    assert body["data"]["path"] == "/api/v1/examples"
    assert body["data"]["errors"] == [
        {"field": "email", "message": "이메일 형식이 올바르지 않습니다."},
        {"field": "password", "message": "비밀번호는 8자 이상이어야 합니다."},
    ]


async def test_ready_endpoint_is_not_exposed_until_it_checks_dependencies() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 404
    assert response.json()["success"] is False


async def test_openapi_schema_is_available() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Boat Backend"


def test_settings_can_override_database_url_without_import_global_session() -> None:
    settings = Settings(database_url="postgresql+asyncpg://test:test@localhost:5432/test")

    assert settings.database_url.endswith("/test")


async def test_database_state_is_created_by_lifespan_not_import() -> None:
    test_app = create_app(
        Settings(database_url="postgresql+asyncpg://test:test@localhost:5432/test")
    )

    assert not hasattr(test_app.state, "engine")
    assert not hasattr(test_app.state, "session_factory")

    async with test_app.router.lifespan_context(test_app):
        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

        assert hasattr(test_app.state, "engine")
        assert hasattr(test_app.state, "session_factory")
        assert response.status_code == 200
