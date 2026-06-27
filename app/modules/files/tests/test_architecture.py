import ast
from pathlib import Path

from app.core.config.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[4]
FILES_ROOT = PROJECT_ROOT / "app" / "modules" / "files"

EXPECTED_FILES = {
    "api/router.py",
    "api/schemas.py",
    "application/commands/upload_file/command.py",
    "application/commands/upload_file/result.py",
    "application/commands/upload_file/use_case.py",
    "application/commands/delete_file/command.py",
    "application/commands/delete_file/use_case.py",
    "application/queries/get_file/query.py",
    "application/queries/get_file/result.py",
    "application/queries/get_file/use_case.py",
    "application/queries/open_file_content/query.py",
    "application/queries/open_file_content/result.py",
    "application/queries/open_file_content/use_case.py",
    "application/ports/file_repository.py",
    "application/ports/file_reference_guard.py",
    "application/ports/object_storage.py",
    "domain/model.py",
    "domain/value_objects.py",
    "domain/exceptions.py",
    "infrastructure/persistence/orm.py",
    "infrastructure/persistence/mapper.py",
    "infrastructure/persistence/repository.py",
    "infrastructure/storage/local.py",
    "dependencies.py",
}

FORBIDDEN_FILES = {
    "application/service.py",
    "application/schemas.py",
    "infrastructure/repository.py",
}

EXPECTED_SETTINGS = {
    "file_storage_backend",
    "file_storage_root",
    "file_max_upload_bytes",
    "file_max_upload_count",
    "file_allowed_content_types",
}


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


def test_files_module_exposes_vertical_slice_layout() -> None:
    missing_files = [
        relative_path
        for relative_path in EXPECTED_FILES
        if not (FILES_ROOT / relative_path).is_file()
    ]
    forbidden_files = [
        relative_path for relative_path in FORBIDDEN_FILES if (FILES_ROOT / relative_path).exists()
    ]

    assert missing_files == []
    assert forbidden_files == []


def test_files_settings_are_registered_on_settings_model() -> None:
    setting_names = set(Settings.model_fields)

    assert EXPECTED_SETTINGS.issubset(setting_names)


def test_files_application_and_domain_do_not_import_foreign_infrastructure() -> None:
    forbidden_prefixes = (
        "app.modules.auth.infrastructure",
        "app.modules.users.infrastructure",
    )
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for root in (FILES_ROOT / "application", FILES_ROOT / "domain")
        for path in root.rglob("*.py")
        if "tests" not in path.parts
        and any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for imported in _imports(path)
            for prefix in forbidden_prefixes
        )
    ]

    assert offending_files == []


def test_files_module_does_not_expose_storage_in_api_contract() -> None:
    public_files = [
        FILES_ROOT / "api" / "router.py",
        FILES_ROOT / "api" / "schemas.py",
    ]
    leaked_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in public_files
        if path.exists()
        and any(term in path.read_text() for term in ("storage_key", "bucket", "cdn", "signed"))
    ]

    assert leaked_files == []
