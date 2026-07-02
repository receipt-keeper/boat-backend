from importlib import import_module
from pathlib import Path
from typing import Final

EXPECTED_DOMAIN_MODELS: Final[dict[str, frozenset[str]]] = {
    "app.modules.credits.domain": frozenset(
        {
            "CreditAction",
            "CreditBalance",
            "CreditCount",
            "CreditReason",
            "CreditTransaction",
            "FeatureKey",
            "UserCredit",
        }
    ),
    "app.modules.usage.domain": frozenset({"OcrUsage", "UsageSnapshot"}),
    "app.modules.notifications.domain.model": frozenset(
        {"NotificationSettings", "UserNotification"}
    ),
}
EXPECTED_DOMAIN_PACKAGE_LAYOUT: Final[dict[str, frozenset[str]]] = {
    "app/modules/credits": frozenset({"domain/__init__.py", "domain/model.py"}),
    "app/modules/usage": frozenset({"domain/__init__.py", "domain/model.py"}),
}
FORBIDDEN_DOMAIN_MODULE_FILES: Final[tuple[Path, ...]] = (
    Path("app/modules", "credits", "domain.py"),
    Path("app/modules", "usage", "domain.py"),
)
EXPECTED_PERSISTENCE_BACKED_DATA: Final[dict[str, frozenset[str]]] = {
    "app.modules.credits.dependencies": frozenset(
        {
            "GetCreditBalanceQueryUseCaseDep",
            "ListCreditTransactionsQueryUseCaseDep",
            "get_credit_balance_query_use_case",
            "get_credit_repository",
            "get_list_credit_transactions_query_use_case",
        }
    ),
    "app.modules.credits.infrastructure.persistence.repository": frozenset(
        {"SqlAlchemyCreditRepository"}
    ),
    "app.modules.notifications.dependencies": frozenset(
        {
            "ListNotificationsQueryUseCaseDep",
            "get_create_notification_command_use_case",
            "get_list_notifications_query_use_case",
            "get_mark_notification_read_command_use_case",
            "get_notification_settings_query_use_case",
            "get_notification_repository",
            "get_update_notification_settings_command_use_case",
        }
    ),
    "app.modules.notifications.infrastructure.persistence.repository": frozenset(
        {"SqlAlchemyNotificationRepository"}
    ),
    "app.modules.usage.dependencies": frozenset(
        {
            "GetUsageSnapshotQueryUseCaseDep",
            "get_usage_snapshot_query_use_case",
        }
    ),
}
EXPECTED_MOCK_DATA: Final[dict[str, frozenset[str]]] = {
    "app.modules.receipts.mock": frozenset(
        {"SAMPLE_FILE_ID", "SAMPLE_RECEIPTS", "receipt_with_id", "sample_receipt"}
    ),
}


def test_mvp_bc_modules_expose_domain_models() -> None:
    for module_name, model_names in EXPECTED_DOMAIN_MODELS.items():
        module = import_module(module_name)
        missing_names = [name for name in model_names if not hasattr(module, name)]
        assert missing_names == []


def test_credits_usage_domain_modules_use_package_layout() -> None:
    missing_files = [
        f"{module_root}/{relative_path}"
        for module_root, relative_paths in EXPECTED_DOMAIN_PACKAGE_LAYOUT.items()
        for relative_path in relative_paths
        if not Path(module_root, relative_path).is_file()
    ]
    forbidden_files = [path.as_posix() for path in FORBIDDEN_DOMAIN_MODULE_FILES if path.exists()]

    assert {"missing": missing_files, "forbidden": forbidden_files} == {
        "missing": [],
        "forbidden": [],
    }


def test_credits_domain_does_not_export_persistence_credit_account() -> None:
    domain_module = import_module("app.modules.credits.domain")

    assert not hasattr(domain_module, "Credit" + "Account")


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


def test_alembic_env_imports_persistence_backed_models() -> None:
    env_source = Path("alembic/env.py").read_text(encoding="utf-8")

    assert "app.modules.credits.infrastructure.persistence" in env_source
    assert "app.modules.notifications.infrastructure.persistence" in env_source
