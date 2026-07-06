import ast
import dataclasses
from importlib import import_module
from pathlib import Path
from typing import Any

from app.core.domain.events import DomainEvent

PROJECT_ROOT = Path(__file__).resolve().parents[4]
CREDITS_ROOT = PROJECT_ROOT / "app" / "modules" / "credits"

EXPECTED_DOMAIN_PACKAGE_FILES = {
    "domain/__init__.py",
    "domain/model.py",
    "domain/events.py",
    "domain/value_objects.py",
}
FORBIDDEN_DOMAIN_FILES = {
    "domain.py",
}
EXPECTED_EVENT_CLASS_NAMES = {
    "CreditGranted",
    "CreditUsed",
    "UserCreditsDeleted",
}
FORBIDDEN_INFRASTRUCTURE_IMPORT_PREFIXES = ("app.modules.credits.infrastructure",)
FORBIDDEN_DOMAIN_IMPORT_PREFIXES = (
    "fastapi",
    "sqlalchemy",
    "app.core.db",
    "app.modules.credits.infrastructure",
)
EXPECTED_PUBLIC_DOMAIN_SYMBOLS = {
    "CreditAction",
    "CreditAmount",
    "CreditBalance",
    "CreditCount",
    "CreditReason",
    "CreditTransaction",
    "FeatureKey",
    "UserCredit",
}
PERSISTENCE_MODEL_NAME = "Credit" + "Account"
ALLOWED_PERSISTENCE_MODEL_REFERENCE_PREFIXES = (
    "app/modules/credits/infrastructure/persistence/",
    "app/modules/credits/tests/",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def _imports_forbidden_prefix(imported: str, forbidden_prefixes: tuple[str, ...]) -> bool:
    return any(
        imported == forbidden or imported.startswith(f"{forbidden}.")
        for forbidden in forbidden_prefixes
    )


def test_credits_domain_uses_package_layout() -> None:
    missing_files = [
        relative_path
        for relative_path in EXPECTED_DOMAIN_PACKAGE_FILES
        if not (CREDITS_ROOT / relative_path).is_file()
    ]
    forbidden_files = [
        relative_path
        for relative_path in FORBIDDEN_DOMAIN_FILES
        if (CREDITS_ROOT / relative_path).exists()
    ]

    assert {"missing": missing_files, "forbidden": forbidden_files} == {
        "missing": [],
        "forbidden": [],
    }


def test_credits_domain_package_re_exports_existing_public_symbols() -> None:
    domain_module = import_module("app.modules.credits.domain")
    missing_symbols = [
        name for name in EXPECTED_PUBLIC_DOMAIN_SYMBOLS if not hasattr(domain_module, name)
    ]

    assert missing_symbols == []


def test_credits_domain_exports_user_credit_aggregate_root() -> None:
    domain_module = import_module("app.modules.credits.domain")

    assert hasattr(domain_module, "UserCredit")


def test_credits_domain_does_not_export_credit_account_persistence_model() -> None:
    domain_module = import_module("app.modules.credits.domain")

    assert not hasattr(domain_module, PERSISTENCE_MODEL_NAME)


def test_credits_application_and_domain_do_not_import_infrastructure() -> None:
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for root in (CREDITS_ROOT / "application", CREDITS_ROOT / "domain")
        for path in root.rglob("*.py")
        if "tests" not in path.parts
        and any(
            _imports_forbidden_prefix(imported, FORBIDDEN_INFRASTRUCTURE_IMPORT_PREFIXES)
            for imported in _imports(path)
        )
    ]

    assert offending_files == []


def test_credits_application_has_no_projection_package() -> None:
    projection_path = CREDITS_ROOT / "application" / ("read" + "_models")
    python_sources = (
        [path.relative_to(PROJECT_ROOT).as_posix() for path in projection_path.rglob("*.py")]
        if projection_path.exists()
        else []
    )

    assert python_sources == []


def test_credits_domain_does_not_import_http_database_or_persistence_adapters() -> None:
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (CREDITS_ROOT / "domain").rglob("*.py")
        if any(
            _imports_forbidden_prefix(imported, FORBIDDEN_DOMAIN_IMPORT_PREFIXES)
            for imported in _imports(path)
        )
    ]

    assert offending_files == []


def test_credit_account_name_stays_outside_domain_sources() -> None:
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in CREDITS_ROOT.rglob("*.py")
        if PERSISTENCE_MODEL_NAME in path.read_text(encoding="utf-8")
        and not path.relative_to(PROJECT_ROOT)
        .as_posix()
        .startswith(ALLOWED_PERSISTENCE_MODEL_REFERENCE_PREFIXES)
    ]

    assert offending_files == []


def test_credits_domain_events_module_declares_only_frozen_domain_events() -> None:
    events_module = import_module("app.modules.credits.domain.events")

    declared_classes = [
        obj
        for name, obj in vars(events_module).items()
        if isinstance(obj, type) and obj.__module__ == events_module.__name__
    ]

    assert {cls.__name__ for cls in declared_classes} == EXPECTED_EVENT_CLASS_NAMES
    for cls in declared_classes:
        assert issubclass(cls, DomainEvent)
        assert dataclasses.is_dataclass(cls)
        dataclass_params: Any = getattr(cls, "__dataclass_params__")  # noqa: B009
        assert dataclass_params.frozen is True


def test_credits_domain_events_import_only_value_objects_and_core_events() -> None:
    events_path = CREDITS_ROOT / "domain" / "events.py"
    allowed_prefixes = (
        "dataclasses",
        "uuid",
        "app.core.domain.events",
        "app.modules.credits.domain.value_objects",
    )
    offending_imports = [
        imported
        for imported in _imports(events_path)
        if not _imports_forbidden_prefix(imported, allowed_prefixes)
    ]

    assert offending_imports == []
