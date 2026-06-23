import ast
from pathlib import Path

from app.core.config.settings import Settings
from app.core.domain.entity import Entity
from app.main import create_app
from app.modules.users.domain.model import User

PROJECT_ROOT = Path(__file__).resolve().parents[4]
USERS_ROOT = PROJECT_ROOT / "app" / "modules" / "users"
APPLICATION_ROOT = USERS_ROOT / "application"
USERS_GUIDANCE = USERS_ROOT / "AGENTS.md"

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

PRD_USERS_PUBLIC_ENDPOINTS = (
    "GET /api/v1/users/me",
    "PATCH /api/v1/users/me",
    "DELETE /api/v1/users/me",
)

# 앱 공개 계약에서 제거된(설정 분리/푸시 알림) 엔드포인트. guidance·OpenAPI에 남으면 안 된다.
RETIRED_USERS_PUBLIC_ENDPOINTS = (
    "PATCH /api/v1/users/me/settings",
    "POST /api/v1/users/me/push-tokens",
    "DELETE /api/v1/users/me/push-tokens/{deviceId}",
)

OPENAPI_TEST_SETTINGS = Settings(
    jwt_secret_key="x" * 48,
    jwt_issuer="boat-backend-test",
    jwt_audience="boat-api-test",
)


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


def test_users_guidance_reserves_prd_public_api_scope() -> None:
    guidance = USERS_GUIDANCE.read_text()

    assert "provision-only" not in guidance
    assert "no public `api/` surface" not in guidance
    assert "Users owns the PRD public mypage API scope" in guidance
    assert all(endpoint in guidance for endpoint in PRD_USERS_PUBLIC_ENDPOINTS)
    # 앱 공개 계약에서 제외된 설정/푸시 엔드포인트는 guidance에 남기지 않는다.
    assert all(endpoint not in guidance for endpoint in RETIRED_USERS_PUBLIC_ENDPOINTS)


def test_users_openapi_exposes_only_app_public_contract() -> None:
    schema = create_app(OPENAPI_TEST_SETTINGS).openapi()
    paths = schema["paths"]
    components = schema["components"]["schemas"]

    me_operations = paths["/api/v1/users/me"]
    assert {"get", "patch", "delete"}.issubset(set(me_operations))

    # 앱 공개 계약에서 제외/이동한 경로는 OpenAPI에 노출되지 않는다.
    assert "/api/v1/users/me/settings" not in paths
    assert "/api/v1/users/me/push-tokens" not in paths
    assert "/api/v1/users/me/push-tokens/{deviceId}" not in paths
    assert "/api/v1/auth/me" not in paths
    assert "RegisterPushTokenRequest" not in components
    assert "RegisterPushTokenResponse" not in components


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


def test_users_module_does_not_import_auth_api_or_infrastructure() -> None:
    forbidden_auth_prefixes = (
        "app.modules.auth.api",
        "app.modules.auth.infrastructure",
    )
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in USERS_ROOT.rglob("*.py")
        if "tests" not in path.parts
        and any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for imported in _imports(path)
            for prefix in forbidden_auth_prefixes
        )
    ]

    assert offending_files == []
