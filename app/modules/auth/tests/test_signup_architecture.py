import ast
from inspect import signature
from pathlib import Path

from app.core.db.session import AsyncSessionDep
from app.modules.auth.dependencies import (
    get_credential_repository,
    get_external_identity_login_synchronizer,
    get_notification_settings_initializer,
    get_user_provisioner,
)
from app.modules.notifications.dependencies import (
    build_update_notification_settings_command_use_case,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
AUTH_ROOT = PROJECT_ROOT / "app" / "modules" / "auth"
NOTIFICATIONS_DEPENDENCIES = PROJECT_ROOT / "app" / "modules" / "notifications" / "dependencies.py"
AUTH_DEPENDENCY_ADAPTERS = AUTH_ROOT / "dependency_adapters.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def _function_call_names(path: Path, function_name: str) -> set[str]:
    tree = ast.parse(path.read_text())
    call_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == function_name:
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    call_names.add(child.func.id)
    return call_names


def test_signup_wiring_shares_one_transaction_session() -> None:
    assert all(
        signature(dependency).parameters["session"].annotation == AsyncSessionDep
        for dependency in (
            get_credential_repository,
            get_external_identity_login_synchronizer,
            get_user_provisioner,
            get_notification_settings_initializer,
        )
    )


def test_signup_cross_module_wiring_defers_inner_commits() -> None:
    auth_dependencies = AUTH_ROOT / "dependencies.py"

    assert {
        "build_resolve_user_for_login_command_use_case",
        "DeferredCommitUnitOfWork",
        "ProvisionUserPortAdapter",
    }.issubset(_function_call_names(auth_dependencies, "get_user_provisioner"))
    assert {
        "build_update_notification_settings_command_use_case",
        "NotificationSettingsInitializerAdapter",
        "DeferredCommitUnitOfWork",
    }.issubset(_function_call_names(auth_dependencies, "get_notification_settings_initializer"))
    assert "SqlAlchemyUnitOfWork" not in _function_call_names(
        auth_dependencies,
        "get_user_provisioner",
    )
    assert "SqlAlchemyUnitOfWork" not in _function_call_names(
        auth_dependencies,
        "get_notification_settings_initializer",
    )
    assert "SqlAlchemyUnitOfWork" not in _function_call_names(
        NOTIFICATIONS_DEPENDENCIES,
        "build_update_notification_settings_command_use_case",
    )


def test_signup_notification_settings_builder_accepts_outer_unit_of_work() -> None:
    assert list(signature(build_update_notification_settings_command_use_case).parameters) == [
        "session",
        "unit_of_work",
    ]


def test_auth_module_does_not_import_notifications_infrastructure() -> None:
    forbidden_prefix = ".".join(("app", "modules", "notifications", "infrastructure"))
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in AUTH_ROOT.rglob("*.py")
        if "tests" not in path.parts
        and any(imported.startswith(forbidden_prefix) for imported in _imports(path))
    ]

    assert offending_files == []


def test_auth_users_runtime_wiring_stays_in_dependencies() -> None:
    assert {
        "app.modules.users.application.commands.resolve_user_for_login.command",
        "app.modules.users.application.commands.resolve_user_for_login.use_case",
    }.issubset(_imports(AUTH_ROOT / "dependencies.py"))
    assert not any(
        imported.startswith("app.modules.users.") for imported in _imports(AUTH_DEPENDENCY_ADAPTERS)
    )


def test_notifications_dependencies_do_not_import_auth_ports() -> None:
    forbidden_prefix = ".".join(("app", "modules", "auth"))

    assert not any(
        imported == forbidden_prefix or imported.startswith(f"{forbidden_prefix}.")
        for imported in _imports(NOTIFICATIONS_DEPENDENCIES)
    )
