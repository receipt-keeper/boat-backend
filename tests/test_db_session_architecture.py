import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULES_ROOT = PROJECT_ROOT / "app" / "modules"
AUTH_CREDENTIAL_REPOSITORY = (
    MODULES_ROOT / "auth" / "infrastructure" / "persistence" / "credential_repository.py"
)
USERS_REPOSITORY = MODULES_ROOT / "users" / "infrastructure" / "persistence" / "repository.py"
USERS_DEPENDENCIES = MODULES_ROOT / "users" / "dependencies.py"
CORE_UOW = PROJECT_ROOT / "app" / "core" / "application" / "unit_of_work.py"
DB_UOW = PROJECT_ROOT / "app" / "core" / "db" / "unit_of_work.py"
TEST_UOW = PROJECT_ROOT / "tests" / "support" / "unit_of_work.py"


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


def test_sqlalchemy_repositories_depend_on_async_session_only() -> None:
    expected_imports = {"sqlalchemy.ext.asyncio.AsyncSession"}
    forbidden_imports = {
        "app.core.db.session.SessionProvider",
        "app.core.db.session.session_scope",
    }

    assert all(
        expected_imports.issubset(_imports(repository))
        for repository in (AUTH_CREDENTIAL_REPOSITORY, USERS_REPOSITORY)
    )
    assert all(
        _imports(repository).isdisjoint(forbidden_imports)
        for repository in (AUTH_CREDENTIAL_REPOSITORY, USERS_REPOSITORY)
    )


def test_users_dependency_uses_core_db_session_dependency() -> None:
    assert "app.core.db.session.AsyncSessionDep" in _imports(USERS_DEPENDENCIES)


def test_modules_do_not_own_sqlalchemy_session_scope_helpers() -> None:
    module_local_session_providers: list[str] = []
    module_local_session_scopes: list[str] = []
    module_direct_session_factories: list[str] = []
    for path in MODULES_ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue

        tree = ast.parse(path.read_text())
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "SessionProvider"
                for target in node.targets
            ):
                module_local_session_providers.append(relative_path)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_session":
                module_local_session_scopes.append(relative_path)
            if isinstance(node, ast.Attribute) and node.attr == "session_factory":
                module_direct_session_factories.append(relative_path)

    assert module_local_session_providers == []
    assert module_local_session_scopes == []
    assert module_direct_session_factories == []


def test_unit_of_work_implementations_explicitly_inherit_port() -> None:
    expected = {
        CORE_UOW: {"DeferredCommitUnitOfWork"},
        DB_UOW: {"SqlAlchemyUnitOfWork"},
        TEST_UOW: {"FakeUnitOfWork"},
    }

    for path, class_names in expected.items():
        tree = ast.parse(path.read_text())
        classes = {
            node.name: {base.id for base in node.bases if isinstance(base, ast.Name)}
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
        }
        assert all("UnitOfWork" in classes[class_name] for class_name in class_names)
