from httpx import ASGITransport, AsyncClient

from app.core.config.settings import Settings
from app.main import create_app


async def test_force_server_error_endpoint_returns_500_failure_envelope() -> None:
    test_app = create_app(Settings(app_name="Boat Backend"))

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        response = await test_client.get("/api/v1/example/server-error")

    body = response.json()

    assert response.status_code == 500
    assert body["success"] is False
    assert body["status"] == 500
    assert body["data"]["message"] == "서버 내부 오류가 발생했습니다."
    assert body["data"]["path"] == "/api/v1/example/server-error"
    assert body["data"]["errors"] == []


def test_force_server_error_endpoint_is_documented_in_openapi() -> None:
    schema = create_app(Settings(app_name="Boat Backend")).openapi()
    operation = schema["paths"]["/api/v1/example/server-error"]["get"]

    assert operation["summary"] == "테스트용 500 오류 발생"
    assert operation["responses"]["500"]["description"] == "서버 내부 오류 강제 발생"
