import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
OCR_ROOT = PROJECT_ROOT / "app" / "modules" / "ocr"
EXPECTED_COMMAND_PACKAGE_FILES = {
    "application/commands/extract_receipt_ocr/__init__.py",
    "application/commands/extract_receipt_ocr/command.py",
    "application/commands/extract_receipt_ocr/use_case.py",
}
FORBIDDEN_APPLICATION_FILES = {
    "application/service.py",
}
FORBIDDEN_APPLICATION_IMPORT_PREFIXES = ("app.modules.ocr.infrastructure",)
FORBIDDEN_RELATIVE_APPLICATION_IMPORT_PREFIXES = ("infrastructure",)
EXPECTED_API_IMPORT_PREFIXES = {
    "app.modules.ocr.application.commands.extract_receipt_ocr.command",
    "app.modules.ocr.dependencies",
}


def test_ocr_application_uses_command_use_case_layout() -> None:
    missing_files = [
        relative_path
        for relative_path in EXPECTED_COMMAND_PACKAGE_FILES
        if not (OCR_ROOT / relative_path).is_file()
    ]
    forbidden_files = [
        relative_path
        for relative_path in FORBIDDEN_APPLICATION_FILES
        if (OCR_ROOT / relative_path).exists()
    ]

    assert {"missing": missing_files, "forbidden": forbidden_files} == {
        "missing": [],
        "forbidden": [],
    }


def test_ocr_api_uses_command_use_case_contract() -> None:
    api_imports = _imports(OCR_ROOT / "api" / "router.py")

    assert EXPECTED_API_IMPORT_PREFIXES.issubset(api_imports)


def test_ocr_application_does_not_import_infrastructure() -> None:
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (OCR_ROOT / "application").rglob("*.py")
        if any(
            _imports_forbidden_prefix(imported, FORBIDDEN_APPLICATION_IMPORT_PREFIXES)
            or _relative_imports_forbidden_prefix(
                imported,
                FORBIDDEN_RELATIVE_APPLICATION_IMPORT_PREFIXES,
            )
            for imported in _imports(path)
        )
    ]

    assert offending_files == []


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            module_name = f"{'.' * node.level}{node.module}"
            imported.add(module_name)
            imported.update(f"{module_name}.{alias.name}" for alias in node.names)
    return imported


def _imports_forbidden_prefix(imported: str, forbidden_prefixes: tuple[str, ...]) -> bool:
    return any(
        imported == forbidden or imported.startswith(f"{forbidden}.")
        for forbidden in forbidden_prefixes
    )


def _relative_imports_forbidden_prefix(
    imported: str,
    forbidden_prefixes: tuple[str, ...],
) -> bool:
    relative_import = imported.lstrip(".")
    return any(
        relative_import == forbidden or relative_import.startswith(f"{forbidden}.")
        for forbidden in forbidden_prefixes
    )
