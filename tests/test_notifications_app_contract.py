from typing import Final

from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.domain.value_objects import (
    NotificationCategory,
    NotificationMessageType,
)
from tests.support.notifications_contract import (
    TEST_SETTINGS,
    TEST_USER_ID,
    create_notifications_contract_app,
)

NOTIFICATION_RESPONSE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "notificationId",
        "category",
        "messageType",
        "kind",
        "title",
        "message",
        "resourceType",
        "resourceId",
        "metadata",
        "createdAt",
        "readAt",
    }
)
NOTIFICATION_SETTINGS_FIELDS: Final[frozenset[str]] = frozenset({"pushEnabled", "marketingConsent"})
NOTIFICATION_SNAKE_CASE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "notification_id",
        "message_type",
        "resource_type",
        "resource_id",
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
    test_app, notifications = create_notifications_contract_app()
    user_metadata = {
        "campaignKey": "user-visible-campaign",
        "landingTarget": "user-visible-target",
        "joinBasedBucket": "user-visible-bucket",
        "scheduledKey": "user-visible-schedule",
        "campaignPolicy": "user-visible-policy",
        "deliveryHistory": "user-visible-history",
        "scheduled_key": "user_visible_schedule",
        "campaign_key": "user_visible_campaign",
        "campaign_policy": "user_visible_policy",
        "delivery_history": "user_visible_history",
        "landing_target": "user_visible_target",
        "join_based_bucket": "user_visible_bucket",
        "productName": "receiptUpload",
        "subCategory": "receiptUpload",
    }
    created = [
        notifications.create(
            CreateNotificationCommand(
                user_id=TEST_USER_ID,
                category=category,
                message_type=message_type,
                kind=kind,
                title=title,
                message=message,
                resource_type=None,
                resource_id=None,
                metadata=metadata,
            )
        )
        for category, message_type, kind, title, message, metadata in (
            (
                NotificationCategory.PRODUCT_MANAGEMENT,
                NotificationMessageType.TRANSACTIONAL,
                "registration_prompt",
                "영수증 등록 안내",
                "영수증을 등록하면 보증 만료 알림을 받을 수 있어요.",
                user_metadata,
            ),
            (
                NotificationCategory.BENEFIT,
                NotificationMessageType.MARKETING,
                "benefit",
                "혜택 안내",
                "이번 달 혜택을 확인해 보세요.",
                {},
            ),
            (
                NotificationCategory.BENEFIT,
                NotificationMessageType.TRANSACTIONAL,
                "credit_prompt",
                "크레딧 안내",
                "분석 가능 횟수를 확인해 보세요.",
                {},
            ),
        )
    ]

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        settings_response = await test_client.get("/api/v1/notifications/settings")
        consent_response = await test_client.patch(
            "/api/v1/notifications/settings",
            json={"marketingConsent": True},
        )
        response = await test_client.get("/api/v1/notifications?limit=2")
        first_next_cursor = response.json()["data"]["pagination"]["nextCursor"]
        next_response = await test_client.get(
            f"/api/v1/notifications?limit=2&cursor={first_next_cursor}"
        )
        read_response = await test_client.patch(
            f"/api/v1/notifications/{created[-1].notification_id}"
        )
        updated_settings_response = await test_client.patch(
            "/api/v1/notifications/settings",
            json={"pushEnabled": False, "marketingConsent": True},
        )
        removed_create_response = await test_client.post(
            "/api/v1/notifications",
            json={},
        )

    body = response.json()
    next_body = next_response.json()
    read_body = read_response.json()
    notification_payloads = (
        [
            {
                "notificationId": str(notification.notification_id),
                "category": notification.category.value,
                "messageType": notification.message_type.value,
                "kind": notification.kind,
                "title": notification.title,
                "message": notification.message,
                "resourceType": notification.resource_type,
                "resourceId": (
                    str(notification.resource_id) if notification.resource_id is not None else None
                ),
                "metadata": notification.metadata,
                "createdAt": notification.created_at.isoformat().replace("+00:00", "Z"),
                "readAt": notification.read_at,
            }
            for notification in created
        ]
        + body["data"]["notifications"]
        + next_body["data"]["notifications"]
        + [read_body["data"]]
    )

    assert all(
        set(notification) == NOTIFICATION_RESPONSE_FIELDS for notification in notification_payloads
    )
    assert all(
        NOTIFICATION_SNAKE_CASE_FIELDS.isdisjoint(notification)
        for notification in notification_payloads
    )
    assert all("userId" not in notification for notification in notification_payloads)
    assert created[0].metadata == user_metadata
    assert response.status_code == 200
    assert [notification["notificationId"] for notification in body["data"]["notifications"]] == [
        str(created[2].notification_id),
        str(created[1].notification_id),
    ]
    assert body["data"]["pagination"] == {
        "nextCursor": (
            f"{created[1].created_at.isoformat().replace('+00:00', 'Z')}|"
            f"{created[1].notification_id}"
        ),
        "hasNext": True,
        "limit": 2,
        "totalCount": 3,
    }
    assert next_response.status_code == 200
    assert next_body["data"]["notifications"][0]["notificationId"] == str(
        created[0].notification_id
    )
    assert next_body["data"]["pagination"] == {
        "nextCursor": None,
        "hasNext": False,
        "limit": 2,
        "totalCount": 3,
    }
    assert read_response.status_code == 200
    assert read_body["data"]["notificationId"] == str(created[2].notification_id)
    assert read_body["data"]["readAt"] is not None
    assert settings_response.status_code == 200
    assert settings_response.json()["data"] == {"pushEnabled": True, "marketingConsent": False}
    assert consent_response.status_code == 200
    assert consent_response.json()["data"] == {"pushEnabled": True, "marketingConsent": True}
    assert updated_settings_response.status_code == 200
    assert updated_settings_response.json()["data"] == {
        "pushEnabled": False,
        "marketingConsent": True,
    }
    assert set(updated_settings_response.json()["data"]) == NOTIFICATION_SETTINGS_FIELDS
    assert removed_create_response.status_code == 405


def test_notifications_openapi_uses_camel_case_contract() -> None:
    schema = create_app(TEST_SETTINGS).openapi()
    schemas = schema["components"]["schemas"]
    notification_fields = set(schemas["NotificationResponse"]["properties"])
    settings_fields = set(schemas["NotificationSettingsResponse"]["properties"])
    update_settings_fields = set(schemas["UpdateNotificationSettingsRequest"]["properties"])

    assert notification_fields == NOTIFICATION_RESPONSE_FIELDS
    assert settings_fields == NOTIFICATION_SETTINGS_FIELDS
    assert update_settings_fields == NOTIFICATION_SETTINGS_FIELDS
    assert NOTIFICATION_SNAKE_CASE_FIELDS.isdisjoint(notification_fields)
    assert NOTIFICATION_SNAKE_CASE_FIELDS.isdisjoint(settings_fields)
    assert NOTIFICATION_SNAKE_CASE_FIELDS.isdisjoint(update_settings_fields)
    assert "CreateNotificationRequest" not in schemas
    assert "SkippedMarketingConsentResponse" not in schemas


def test_notifications_retired_paths_are_absent_from_openapi() -> None:
    paths = set(create_app(TEST_SETTINGS).openapi()["paths"])

    assert FORBIDDEN_NOTIFICATION_PATHS.isdisjoint(paths)


def test_notifications_delete_route_is_exposed_with_patch_route() -> None:
    paths = create_app(TEST_SETTINGS).openapi()["paths"]

    assert set(paths["/api/v1/notifications/{notification_id}"]) == {"patch", "delete"}
