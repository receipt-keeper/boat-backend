from typing import Final

from httpx import ASGITransport, AsyncClient

from app.main import create_app
from tests.support.notifications_contract import (
    TEST_SETTINGS,
    TEST_USER_ID,
    create_notifications_contract_app,
)

NOTIFICATION_RESPONSE_FIELDS: Final[frozenset[str]] = frozenset(
    {"notificationId", "kind", "message", "targetType", "targetId", "createdAt", "readAt"}
)
NOTIFICATION_SETTINGS_FIELDS: Final[frozenset[str]] = frozenset({"pushEnabled", "marketingConsent"})
NOTIFICATION_SNAKE_CASE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "notification_id",
        "target_type",
        "target_id",
        "created_at",
        "read_at",
        "push_enabled",
        "marketing_consent",
        "user_id",
    }
)
FORBIDDEN_NOTIFICATION_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/api/v1/notifications/device-token",
        "/api/v1/notification-reads/{notification_id}",
        "/api/v1/notification-settings",
    }
)


async def test_notifications_match_cursor_paging_contract() -> None:
    test_app = create_notifications_contract_app()
    payloads = [
        {
            "kind": "registration_prompt",
            "message": "영수증을 등록하면 보증 만료 알림을 받을 수 있어요.",
            "targetType": "receiptUpload",
            "targetId": None,
        },
        {"kind": "benefit", "message": "이번 달 혜택을 확인해 보세요.", "targetType": "none"},
        {
            "kind": "credit_prompt",
            "message": "분석 가능 횟수를 확인해 보세요.",
            "targetType": "none",
        },
    ]

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        create_responses = [
            await test_client.post("/api/v1/notifications", json=payload) for payload in payloads
        ]
        response = await test_client.get("/api/v1/notifications?limit=2")
        first_next_cursor = response.json()["data"]["pagination"]["nextCursor"]
        next_response = await test_client.get(
            f"/api/v1/notifications?limit=2&cursor={first_next_cursor}"
        )
        read_response = await test_client.patch(
            f"/api/v1/notifications/{create_responses[-1].json()['data']['notificationId']}"
        )
        settings_response = await test_client.get("/api/v1/notifications/settings")
        updated_settings_response = await test_client.patch(
            "/api/v1/notifications/settings",
            json={"pushEnabled": False, "marketingConsent": True},
        )
        rejected_create_response = await test_client.post(
            "/api/v1/notifications",
            json=payloads[0] | {"userId": str(TEST_USER_ID)},
        )

    created = [create_response.json()["data"] for create_response in create_responses]
    body = response.json()
    next_body = next_response.json()
    read_body = read_response.json()
    notification_payloads = created + body["data"]["notifications"] + [read_body["data"]]

    assert [create_response.status_code for create_response in create_responses] == [201, 201, 201]
    assert all(
        set(notification) == NOTIFICATION_RESPONSE_FIELDS for notification in notification_payloads
    )
    assert all(
        NOTIFICATION_SNAKE_CASE_FIELDS.isdisjoint(notification)
        for notification in notification_payloads
    )
    assert all("userId" not in notification for notification in created)
    assert response.status_code == 200
    assert [notification["notificationId"] for notification in body["data"]["notifications"]] == [
        created[2]["notificationId"],
        created[1]["notificationId"],
    ]
    assert body["data"]["pagination"] == {
        "nextCursor": f"{created[1]['createdAt']}|{created[1]['notificationId']}",
        "hasNext": True,
        "limit": 2,
        "totalCount": 3,
    }
    assert next_response.status_code == 200
    assert next_body["data"]["notifications"][0]["notificationId"] == created[0]["notificationId"]
    assert next_body["data"]["pagination"] == {
        "nextCursor": None,
        "hasNext": False,
        "limit": 2,
        "totalCount": 3,
    }
    assert read_response.status_code == 200
    assert read_body["data"]["notificationId"] == created[2]["notificationId"]
    assert read_body["data"]["readAt"] is not None
    assert settings_response.status_code == 200
    assert settings_response.json()["data"] == {"pushEnabled": True, "marketingConsent": False}
    assert updated_settings_response.status_code == 200
    assert updated_settings_response.json()["data"] == {
        "pushEnabled": False,
        "marketingConsent": True,
    }
    assert set(updated_settings_response.json()["data"]) == NOTIFICATION_SETTINGS_FIELDS
    assert rejected_create_response.status_code == 422


def test_notifications_openapi_uses_camel_case_contract() -> None:
    schema = create_app(TEST_SETTINGS).openapi()
    schemas = schema["components"]["schemas"]
    notification_fields = set(schemas["NotificationResponse"]["properties"])
    create_fields = set(schemas["CreateNotificationRequest"]["properties"])
    settings_fields = set(schemas["NotificationSettingsResponse"]["properties"])
    update_settings_fields = set(schemas["UpdateNotificationSettingsRequest"]["properties"])

    assert notification_fields == NOTIFICATION_RESPONSE_FIELDS
    assert create_fields == {"kind", "message", "targetType", "targetId"}
    assert settings_fields == NOTIFICATION_SETTINGS_FIELDS
    assert update_settings_fields == NOTIFICATION_SETTINGS_FIELDS
    assert {"userId", "createdAt", "readAt"}.isdisjoint(create_fields)
    assert NOTIFICATION_SNAKE_CASE_FIELDS.isdisjoint(notification_fields)
    assert NOTIFICATION_SNAKE_CASE_FIELDS.isdisjoint(create_fields)
    assert NOTIFICATION_SNAKE_CASE_FIELDS.isdisjoint(settings_fields)
    assert NOTIFICATION_SNAKE_CASE_FIELDS.isdisjoint(update_settings_fields)


def test_notifications_retired_paths_are_absent_from_openapi() -> None:
    paths = set(create_app(TEST_SETTINGS).openapi()["paths"])

    assert FORBIDDEN_NOTIFICATION_PATHS.isdisjoint(paths)
