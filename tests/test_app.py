from httpx import ASGITransport, AsyncClient

from app.core.config.settings import Settings
from app.main import create_app


async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_endpoint_is_not_exposed_until_it_checks_dependencies(
    client: AsyncClient,
) -> None:
    response = await client.get("/ready")

    assert response.status_code == 404
    assert response.json()["success"] is False


async def test_openapi_schema_is_available() -> None:
    # 로컬 .env의 APP_NAME에 좌우되지 않도록 설정을 명시 주입한다
    test_app = create_app(Settings(app_name="Boat Backend"))

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as test_client:
        response = await test_client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Boat Backend"


def test_notifications_openapi_exposes_create_without_alias_routes() -> None:
    schema = create_app(Settings(app_name="Boat Backend")).openapi()
    paths = schema["paths"]

    assert set(paths["/api/v1/notifications"]) == {"get", "post"}
    assert set(paths["/api/v1/notifications/{notification_id}"]) == {"patch"}
    assert set(paths["/api/v1/notifications/settings"]) == {"get", "patch"}
    assert set(paths["/api/v1/notifications/devices"]) == {"put"}
    assert set(paths["/api/v1/notifications/devices/{token}"]) == {"delete"}
    assert "/api/v1/notifications/device-token" not in paths
    assert "/api/v1/notification-reads/{notification_id}" not in paths
    assert "/api/v1/notification-settings" not in paths


async def test_unhandled_exception_uses_failure_envelope() -> None:
    test_app = create_app(Settings())

    @test_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    # Exception 핸들러는 응답 전송 후 예외를 다시 던지므로(Starlette 동작) 전파를 끈다
    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        response = await test_client.get("/boom")

    body = response.json()

    assert response.status_code == 500
    assert body["success"] is False
    assert body["status"] == 500
    assert body["data"]["message"] == "서버 내부 오류가 발생했습니다."
    assert body["data"]["path"] == "/boom"
    assert body["data"]["errors"] == []


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
        ) as test_client:
            response = await test_client.get("/health")

        assert hasattr(test_app.state, "engine")
        assert hasattr(test_app.state, "session_factory")
        assert response.status_code == 200
