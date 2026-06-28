from importlib import import_module
from pathlib import Path
from typing import Final

EXPECTED_DOMAIN_MODELS: Final[dict[str, frozenset[str]]] = {
    "app.modules.credits.domain": frozenset(
        {"CreditBalance", "CreditTransaction", "CreditAction", "CreditReason"}
    ),
    "app.modules.usage.domain": frozenset({"UsageSnapshot", "ReceiptAnalysisUsage"}),
    "app.modules.notifications.domain.model": frozenset(
        {"NotificationSettings", "UserNotification"}
    ),
}
EXPECTED_PERSISTENCE_BACKED_DATA: Final[dict[str, frozenset[str]]] = {
    "app.modules.notifications.dependencies": frozenset(
        {
            "ListNotificationsQueryUseCaseDep",
            "get_create_notification_command_use_case",
            "get_list_notifications_query_use_case",
            "get_notification_repository",
            "get_notification_settings_query_use_case",
        }
    ),
    "app.modules.notifications.infrastructure.persistence.repository": frozenset(
        {"SqlAlchemyNotificationRepository"}
    ),
}
EXPECTED_MOCK_DATA: Final[dict[str, frozenset[str]]] = {
    "app.modules.credits.mock": frozenset({"SAMPLE_CREDIT_BALANCE", "SAMPLE_CREDIT_TRANSACTIONS"}),
    "app.modules.receipts.mock": frozenset(
        {"SAMPLE_FILE_ID", "SAMPLE_RECEIPTS", "receipt_with_id", "sample_receipt"}
    ),
    "app.modules.usage.mock": frozenset({"SAMPLE_USAGE"}),
}


def test_mvp_bc_modules_expose_domain_models() -> None:
    for module_name, model_names in EXPECTED_DOMAIN_MODELS.items():
        module = import_module(module_name)
        missing_names = [name for name in model_names if not hasattr(module, name)]
        assert missing_names == []


def test_mvp_incomplete_api_modules_expose_mock_data() -> None:
    for module_name, mock_names in EXPECTED_MOCK_DATA.items():
        module = import_module(module_name)
        missing_names = [name for name in mock_names if not hasattr(module, name)]
        assert missing_names == []


def test_persistence_backed_api_modules_expose_application_contracts() -> None:
    for module_name, contract_names in EXPECTED_PERSISTENCE_BACKED_DATA.items():
        module = import_module(module_name)
        missing_names = [name for name in contract_names if not hasattr(module, name)]
        assert missing_names == []


def test_alembic_env_imports_persistence_backed_notification_models() -> None:
    env_source = Path("alembic/env.py").read_text(encoding="utf-8")

    assert "app.modules.notifications.infrastructure.persistence" in env_source
