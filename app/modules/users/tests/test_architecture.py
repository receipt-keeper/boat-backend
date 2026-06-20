import ast
from pathlib import Path

from app.core.domain.entity import Entity
from app.modules.users.domain.model import User

PROJECT_ROOT = Path(__file__).resolve().parents[4]
USERS_ROOT = PROJECT_ROOT / "app" / "modules" / "users"


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


def test_users_domain_does_not_import_persistence_frameworks() -> None:
    domain_imports = _imports(USERS_ROOT / "domain" / "model.py")

    assert "sqlalchemy" not in domain_imports
    assert "sqlalchemy.orm" not in domain_imports
    assert "sqlalchemy.dialects.postgresql" not in domain_imports
    assert "app.core.db.base" not in domain_imports
