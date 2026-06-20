import ast
from pathlib import Path

from app.core.domain.entity import Entity
from app.modules.users.domain.model import User

PROJECT_ROOT = Path(__file__).resolve().parents[4]
USERS_ROOT = PROJECT_ROOT / "app" / "modules" / "users"
APPLICATION_ROOT = USERS_ROOT / "application"

EXPECTED_USERS_FILES = {
    "application/commands/provision/command.py",
    "application/commands/provision/result.py",
    "application/commands/provision/use_case.py",
    "application/commands/delete/command.py",
    "application/commands/delete/use_case.py",
    "application/ports/user_repository.py",
}

FORBIDDEN_USERS_FILES = {
    "application/provision/schemas.py",
    "application/provision/use_case.py",
    "application/delete/schemas.py",
    "application/delete/use_case.py",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_users_domain_model_uses_core_entity_base() -> None:
    assert issubclass(User, Entity)


def test_users_file_structure_exposes_command_flows() -> None:
    missing_files = [
        relative_path
        for relative_path in EXPECTED_USERS_FILES
        if not (USERS_ROOT / relative_path).is_file()
    ]
    forbidden_files = [
        relative_path
        for relative_path in FORBIDDEN_USERS_FILES
        if (USERS_ROOT / relative_path).exists()
    ]

    assert missing_files == []
    assert forbidden_files == []


def test_users_application_flow_classes_use_command_use_case_names() -> None:
    forbidden_class_names = {"DeleteUser" + "UseCase", "ProvisionUser" + "UseCase"}
    discovered_forbidden_classes = [
        f"{path.relative_to(PROJECT_ROOT).as_posix()}::{node.name}"
        for path in APPLICATION_ROOT.rglob("*.py")
        if "tests" not in path.parts
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.ClassDef) and node.name in forbidden_class_names
    ]

    assert discovered_forbidden_classes == []


def test_users_domain_does_not_import_persistence_frameworks() -> None:
    domain_imports = _imports(USERS_ROOT / "domain" / "model.py")

    assert "sqlalchemy" not in domain_imports
    assert "sqlalchemy.orm" not in domain_imports
    assert "sqlalchemy.dialects.postgresql" not in domain_imports
    assert "app.core.db.base" not in domain_imports
