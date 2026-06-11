from collections.abc import Callable
from uuid import UUID, uuid4

from httpx import AsyncClient

from app.modules.examples.application.service import ExampleUserService
from app.modules.examples.domain.exceptions import ExampleUserNotFoundError
from app.modules.examples.domain.model import ExampleUser
from app.modules.examples.infrastructure.repository import ExampleUserRepository


class InMemoryExampleUserService:
    def __init__(self) -> None:
        self._users: dict[UUID, ExampleUser] = {}

    async def get_example_user(self, example_user_id: UUID) -> ExampleUser:
        example_user = self._users.get(example_user_id)
        if example_user is None:
            raise ExampleUserNotFoundError(example_user_id)

        return example_user

    async def create_example_user(self, *, nickname: str, email: str, password: str) -> ExampleUser:
        example_user = ExampleUser.create(nickname=nickname, email=email, password=password)
        self._users[example_user.id] = example_user
        return example_user


async def test_example_user_endpoints_use_success_envelope(
    client: AsyncClient,
    override_example_user_service: Callable[[object], None],
) -> None:
    override_example_user_service(InMemoryExampleUserService())

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


async def test_domain_validation_errors_carry_case_specific_messages(
    client: AsyncClient,
    override_example_user_service: Callable[[object], None],
) -> None:
    override_example_user_service(ExampleUserService(ExampleUserRepository()))

    invalid_email_response = await client.post(
        "/api/v1/examples",
        json={
            "nickname": "test-user",
            "email": "invalid",
            "password": "password123",
        },
    )
    weak_password_response = await client.post(
        "/api/v1/examples",
        json={
            "nickname": "test-user",
            "email": "test@test.com",
            "password": "short",
        },
    )

    invalid_email_body = invalid_email_response.json()
    assert invalid_email_response.status_code == 422
    assert invalid_email_body["success"] is False
    assert invalid_email_body["status"] == 422
    assert invalid_email_body["data"]["message"] == "입력값이 올바르지 않습니다."
    assert invalid_email_body["data"]["path"] == "/api/v1/examples"
    assert invalid_email_body["data"]["errors"] == [
        {"field": "email", "message": "이메일 형식이 올바르지 않습니다."},
    ]

    weak_password_body = weak_password_response.json()
    assert weak_password_response.status_code == 422
    assert weak_password_body["data"]["message"] == "입력값이 올바르지 않습니다."
    assert weak_password_body["data"]["errors"] == [
        {"field": "password", "message": "비밀번호는 8자 이상이어야 합니다."},
    ]


async def test_domain_validation_collects_all_failed_fields(
    client: AsyncClient,
    override_example_user_service: Callable[[object], None],
) -> None:
    override_example_user_service(ExampleUserService(ExampleUserRepository()))

    response = await client.post(
        "/api/v1/examples",
        json={
            "nickname": "",
            "email": "invalid",
            "password": "short",
        },
    )

    body = response.json()

    assert response.status_code == 422
    assert body["data"]["message"] == "입력값이 올바르지 않습니다."
    assert body["data"]["errors"] == [
        {"field": "nickname", "message": "닉네임은 1자 이상 64자 이하여야 합니다."},
        {"field": "email", "message": "이메일 형식이 올바르지 않습니다."},
        {"field": "password", "message": "비밀번호는 8자 이상이어야 합니다."},
    ]


async def test_malformed_request_uses_validation_envelope(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/examples",
        json={"nickname": "test-user"},
    )

    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["message"] == "요청 값이 올바르지 않습니다."
    assert body["data"]["path"] == "/api/v1/examples"
    assert body["data"]["errors"] == [
        {"field": "email", "message": "Field required"},
        {"field": "password", "message": "Field required"},
    ]


async def test_module_error_uses_global_failure_envelope(
    client: AsyncClient,
    override_example_user_service: Callable[[object], None],
) -> None:
    override_example_user_service(InMemoryExampleUserService())
    missing_id = uuid4()

    response = await client.get(f"/api/v1/examples/{missing_id}")

    body = response.json()

    assert response.status_code == 404
    assert body["success"] is False
    assert body["status"] == 404
    assert body["data"]["message"] == "예시 사용자를 찾을 수 없습니다."
    assert body["data"]["path"] == f"/api/v1/examples/{missing_id}"
    assert body["data"]["errors"] == []


async def test_openapi_documents_actual_error_responses(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()

    create_responses = schema["paths"]["/api/v1/examples"]["post"]["responses"]
    get_responses = schema["paths"]["/api/v1/examples/{example_user_id}"]["get"]["responses"]

    assert "422" in create_responses
    assert "422" in get_responses
    assert "404" in get_responses
    # 422 응답 본문은 FastAPI 기본 HTTPValidationError가 아니라 실패 envelope 스키마다
    create_422_schema = create_responses["422"]["content"]["application/json"]["schema"]
    assert create_422_schema["$ref"].endswith("CommonResponse_ApiErrorData_")
