from app.modules.notifications.domain.value_objects import NotificationCategory


def test_notification_category_values_are_stable_codes() -> None:
    assert {category.value for category in NotificationCategory} == {
        "product_management",
        "warranty",
        "benefit",
    }
