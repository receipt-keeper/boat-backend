import ast
from inspect import signature
from pathlib import Path

from app.core.config.settings import Settings
from app.core.db.session import AsyncSessionDep
from app.main import create_app
from app.modules.auth.dependencies import (
    get_credential_repository,
    get_external_identity_login_synchronizer,
    get_notification_settings_initializer,
    get_signup_promotion_redeemer,
    get_user_provisioner,
)
from app.modules.notifications.dependencies import (
    build_update_notification_settings_command_use_case,
)
from app.modules.promotions.api.schemas import PromotionQueryContext
from app.modules.promotions.dependencies import build_redeem_signup_promotion_command_use_case

PROJECT_ROOT = Path(__file__).resolve().parents[4]
AUTH_ROOT = PROJECT_ROOT / "app" / "modules" / "auth"
PROMOTIONS_ROOT = PROJECT_ROOT / "app" / "modules" / "promotions"
NOTIFICATIONS_DEPENDENCIES = PROJECT_ROOT / "app" / "modules" / "notifications" / "dependencies.py"
AUTH_DEPENDENCY_ADAPTERS = AUTH_ROOT / "dependency_adapters.py"
SIGNUP_USE_CASE = AUTH_ROOT / "application" / "commands" / "signup" / "use_case.py"


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
            get_signup_promotion_redeemer,
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
    assert {
        "build_redeem_signup_promotion_command_use_case",
        "DeferredCommitUnitOfWork",
        "SignupPromotionRedeemerAdapter",
    }.issubset(_function_call_names(auth_dependencies, "get_signup_promotion_redeemer"))
    assert "SqlAlchemyUnitOfWork" not in _function_call_names(
        auth_dependencies,
        "get_signup_promotion_redeemer",
    )


def test_signup_notification_settings_builder_accepts_outer_unit_of_work() -> None:
    assert list(signature(build_update_notification_settings_command_use_case).parameters) == [
        "session",
        "unit_of_work",
    ]


def test_signup_promotion_builder_accepts_shared_session_and_outer_unit_of_work() -> None:
    assert list(signature(build_redeem_signup_promotion_command_use_case).parameters) == [
        "session",
        "unit_of_work",
    ]


def test_signup_use_case_has_no_direct_credit_grant_dependency() -> None:
    source = SIGNUP_USE_CASE.read_text()

    assert "CreditInitializer" not in source
    assert "GrantCredit" not in source


def test_signup_use_case_delegates_promotion_policy_to_its_port() -> None:
    imported = _imports(SIGNUP_USE_CASE)
    source_tree = ast.parse(SIGNUP_USE_CASE.read_text())
    forbidden_names = {
        "CreditInitializer",
        "CreditReason",
        "CreditSourceType",
        "GrantCreditCommand",
        "MONTHLY_OCR_ALLOWANCE",
        "EVENT_OCR_ALLOWANCE",
    }

    assert (
        "app.modules.auth.application.ports.signup_promotion_redeemer.SignupPromotionRedeemer"
        in imported
    )
    assert not {
        imported_module
        for imported_module in imported
        if imported_module.startswith("app.modules.credits.")
        or imported_module.startswith("app.modules.promotions.")
    }
    assert not {
        node.id
        for node in ast.walk(source_tree)
        if isinstance(node, ast.Name) and node.id in forbidden_names
    }
    assert 5 not in {
        node.value
        for node in ast.walk(source_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, int)
    }


def test_signup_promotion_stays_internal_to_public_redemption_contracts() -> None:
    schema = create_app(Settings(app_name="Boat Backend", outbox_poller_enabled=False)).openapi()
    promotion_paths = {
        path: operations
        for path, operations in schema["paths"].items()
        if path.startswith("/api/v1/promotions")
    }
    public_redeemer_sources = (
        PROMOTIONS_ROOT
        / "application"
        / "commands"
        / "create_promotion_redemption"
        / "use_case.py",
        PROMOTIONS_ROOT
        / "application"
        / "commands"
        / "create_promotion_code_redemption"
        / "use_case.py",
    )
    signup_redeemer_source = (
        PROMOTIONS_ROOT / "application" / "commands" / "redeem_signup_promotion" / "use_case.py"
    ).read_text(encoding="utf-8")

    assert {context.value for context in PromotionQueryContext} == {"recharge"}
    assert "beneficiary" not in str(promotion_paths).casefold()
    assert not {
        path
        for path in promotion_paths
        if any(
            term in path.casefold()
            for term in ("signup", "beneficiary", "job", "cron", "backfill", "admin")
        )
    }
    assert not {
        path
        for path in schema["paths"]
        if any(term in path.casefold() for term in ("job", "cron", "backfill", "admin"))
    }
    assert "context=PromotionContext.SIGNUP" in signup_redeemer_source
    assert "find_redemption_by_promotion_and_beneficiary" in signup_redeemer_source
    for source_path in public_redeemer_sources:
        source = source_path.read_text(encoding="utf-8")
        assert "case PromotionContext.SIGNUP:" in source
        assert "raise PromotionNotFoundError()" in source


def test_auth_module_does_not_import_notifications_infrastructure() -> None:
    forbidden_prefix = ".".join(("app", "modules", "notifications", "infrastructure"))
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in AUTH_ROOT.rglob("*.py")
        if "tests" not in path.parts
        and any(imported.startswith(forbidden_prefix) for imported in _imports(path))
    ]

    assert offending_files == []


def test_auth_module_does_not_import_promotions_infrastructure() -> None:
    forbidden_prefix = ".".join(("app", "modules", "promotions", "infrastructure"))
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
