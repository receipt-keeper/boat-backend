import ast
from importlib import import_module
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
USAGE_ROOT = PROJECT_ROOT / "app" / "modules" / "usage"

EXPECTED_DOMAIN_PACKAGE_FILES = {
    "domain/__init__.py",
    "domain/model.py",
}
FORBIDDEN_DOMAIN_FILES = {
    "domain.py",
}
FORBIDDEN_INFRASTRUCTURE_IMPORT_PREFIXES = (
    "app.modules.credits.infrastructure",
    "app.modules.usage.infrastructure",
)
FORBIDDEN_DOMAIN_IMPORT_PREFIXES = (
    "fastapi",
    "sqlalchemy",
    "app.core.db",
    "app.modules.credits.infrastructure",
    "app.modules.usage.infrastructure",
)
EXPECTED_PUBLIC_DOMAIN_SYMBOLS = {
    "OcrUsage",
    "UsageSnapshot",
}


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


def test_usage_domain_uses_package_layout() -> None:
    missing_files = [
        relative_path
        for relative_path in EXPECTED_DOMAIN_PACKAGE_FILES
        if not (USAGE_ROOT / relative_path).is_file()
    ]
    forbidden_files = [
        relative_path
        for relative_path in FORBIDDEN_DOMAIN_FILES
        if (USAGE_ROOT / relative_path).exists()
    ]

    assert {"missing": missing_files, "forbidden": forbidden_files} == {
        "missing": [],
        "forbidden": [],
    }


def test_usage_domain_package_re_exports_existing_public_symbols() -> None:
    domain_module = import_module("app.modules.usage.domain")
    missing_symbols = [
        name for name in EXPECTED_PUBLIC_DOMAIN_SYMBOLS if not hasattr(domain_module, name)
    ]

    assert missing_symbols == []


def test_usage_application_and_domain_do_not_import_infrastructure() -> None:
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for root in (USAGE_ROOT / "application", USAGE_ROOT / "domain")
        for path in root.rglob("*.py")
        if "tests" not in path.parts
        and any(
            _imports_forbidden_prefix(imported, FORBIDDEN_INFRASTRUCTURE_IMPORT_PREFIXES)
            for imported in _imports(path)
        )
    ]

    assert offending_files == []


def test_usage_domain_does_not_import_http_database_or_persistence_adapters() -> None:
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (USAGE_ROOT / "domain").rglob("*.py")
        if any(
            _imports_forbidden_prefix(imported, FORBIDDEN_DOMAIN_IMPORT_PREFIXES)
            for imported in _imports(path)
        )
    ]

    assert offending_files == []
