import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[4]
APP_MODULES_ROOT = PROJECT_ROOT / "app" / "modules"
NOTIFICATIONS_ROOT = APP_MODULES_ROOT / "notifications"
CREATE_DUE_NOTIFICATIONS_ROOT = (
    NOTIFICATIONS_ROOT / "application" / "commands" / "create_due_notifications"
)
SCHEDULER_AGNOSTIC_FILES = (
    NOTIFICATIONS_ROOT / "domain" / "model.py",
    NOTIFICATIONS_ROOT / "application" / "commands" / "create_notification" / "command.py",
    NOTIFICATIONS_ROOT / "application" / "ports" / "notification_repository.py",
)


def test_due_notification_flow_does_not_invoke_fcm_directly() -> None:
    due_notification_paths = (
        *tuple(CREATE_DUE_NOTIFICATIONS_ROOT.glob("*.py")),
        NOTIFICATIONS_ROOT / "application" / "due_notification.py",
        NOTIFICATIONS_ROOT / "application" / "warranty_expiry_notifications.py",
        NOTIFICATIONS_ROOT / "application" / "receipt_reminder_notifications.py",
        NOTIFICATIONS_ROOT / "jobs" / "schedule_push_notifications.py",
    )
    forbidden_terms = (
        "firebase_admin",
        "messaging",
        "FcmPushSender",
        "DisabledPushSender",
        "get_push_sender",
        "PushSender",
        "infrastructure.fcm",
        "send_notification_push",
    )

    for path in due_notification_paths:
        source = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in source, f"{path.relative_to(PROJECT_ROOT)} imports {term}"


def test_app_main_does_not_wire_notification_scheduler_loop_or_route() -> None:
    source = (PROJECT_ROOT / "app" / "main.py").read_text(encoding="utf-8")

    assert "schedule_push_notifications" not in source
    assert "scheduler_dependencies" not in source
    assert "build_schedule_push_notifications_command_use_case" not in source


def test_due_notification_flow_does_not_depend_on_credits_or_foreign_repositories() -> None:
    due_notification_paths = (
        *tuple(CREATE_DUE_NOTIFICATIONS_ROOT.glob("*.py")),
        NOTIFICATIONS_ROOT / "application" / "due_notification.py",
        NOTIFICATIONS_ROOT / "application" / "warranty_expiry_notifications.py",
        NOTIFICATIONS_ROOT / "application" / "receipt_reminder_notifications.py",
        NOTIFICATIONS_ROOT / "jobs" / "schedule_push_notifications.py",
    )

    forbidden_imports = (
        "app.modules.credits",
        "ReceiptRepository",
        "UserRepository",
        "receipt_repository",
        "user_repository",
    )
    for path in due_notification_paths:
        source = path.read_text(encoding="utf-8")
        for forbidden_import in forbidden_imports:
            assert forbidden_import not in source, path.relative_to(PROJECT_ROOT)


def test_due_notification_command_package_has_only_public_command_files() -> None:
    assert not (
        NOTIFICATIONS_ROOT / "application" / "commands" / "schedule_push_notifications"
    ).exists()
    assert tuple(
        sorted(path.name for path in CREATE_DUE_NOTIFICATIONS_ROOT.iterdir() if path.is_file())
    ) == (
        "__init__.py",
        "command.py",
        "result.py",
        "use_case.py",
    )


def test_due_notification_builder_has_no_fcm_or_foreign_repository_dependency() -> None:
    source = _function_source(
        NOTIFICATIONS_ROOT / "dependencies.py",
        "build_create_due_notifications_command_use_case",
    )
    for forbidden_term in (
        "FcmPushSender",
        "firebase_admin",
        "get_push_sender",
        "ReceiptRepository",
        "UserRepository",
        "build_receipt_repository",
        "build_user_repository",
    ):
        assert forbidden_term not in source


def test_notification_schedule_rule_product_code_has_no_campaign_policy_names() -> None:
    violations: list[str] = []
    forbidden_terms = (
        "campaign_policy",
        "CampaignPolicy",
        "campaign policy",
        "campaign-policy",
    )
    metadata_guard_path = NOTIFICATIONS_ROOT / "api" / "schemas.py"

    for path in _production_notification_files():
        if path == metadata_guard_path:
            continue
        relative_path = path.relative_to(PROJECT_ROOT)
        path_text = str(relative_path)
        if any(term in path_text for term in forbidden_terms):
            violations.append(path_text)
            continue

        source = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            if term in source:
                violations.append(f"{relative_path} contains {term}")

    assert violations == []


def test_notification_core_create_flow_stays_scheduler_agnostic() -> None:
    forbidden_terms = (
        "NotificationScheduleRule",
        "NotificationScheduleOccurrence",
        "schedule_rule",
        "schedule_occurrence",
        "campaign_key",
    )

    for path in SCHEDULER_AGNOSTIC_FILES:
        source = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in source, f"{path.relative_to(PROJECT_ROOT)} contains {term}"


def test_modules_do_not_import_other_bounded_context_infrastructure() -> None:
    violations: list[str] = []
    for path in _production_module_files():
        module_name = path.relative_to(APP_MODULES_ROOT).parts[0]
        for imported_module in _imported_modules(path):
            parts = imported_module.split(".")
            if (
                len(parts) >= 4
                and parts[0] == "app"
                and parts[1] == "modules"
                and parts[3] == "infrastructure"
                and parts[2] != module_name
            ):
                violations.append(f"{path.relative_to(PROJECT_ROOT)} -> {imported_module}")

    assert violations == []


def _production_module_files() -> tuple[Path, ...]:
    return tuple(
        path
        for path in APP_MODULES_ROOT.rglob("*.py")
        if "tests" not in path.relative_to(APP_MODULES_ROOT).parts
    )


def _production_notification_files() -> tuple[Path, ...]:
    return tuple(
        path
        for path in NOTIFICATIONS_ROOT.rglob("*.py")
        if "tests" not in path.relative_to(NOTIFICATIONS_ROOT).parts
        and "__pycache__" not in path.relative_to(NOTIFICATIONS_ROOT).parts
    )


def _imported_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return tuple(modules)


def _function_source(path: Path, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"{path.relative_to(PROJECT_ROOT)}에 {function_name}가 없습니다.")
