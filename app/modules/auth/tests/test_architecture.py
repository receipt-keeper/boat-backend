import ast
import importlib
from pathlib import Path

from app.core.domain.entity import Entity
from app.modules.auth.domain.model import ExternalIdentity, RefreshToken, UserCredential

PROJECT_ROOT = Path(__file__).resolve().parents[4]
AUTH_ROOT = PROJECT_ROOT / "app" / "modules" / "auth"
APPLICATION_ROOT = AUTH_ROOT / "application"
AUTH_GUIDANCE = AUTH_ROOT / "AGENTS.md"
AUTH_ROUTER = AUTH_ROOT / "api" / "router.py"

EXPECTED_AUTH_FILES = {
    "application/commands/login/command.py",
    "application/commands/login/result.py",
    "application/commands/login/use_case.py",
    "application/commands/signup/command.py",
    "application/commands/signup/result.py",
    "application/commands/signup/use_case.py",
    "application/commands/refresh/command.py",
    "application/commands/refresh/result.py",
    "application/commands/refresh/use_case.py",
    "application/commands/logout/command.py",
    "application/commands/logout/use_case.py",
    "application/commands/withdraw/command.py",
    "application/commands/withdraw/use_case.py",
    "application/queries/current_principal/query.py",
    "application/queries/current_principal/use_case.py",
    "application/ports/credential_repository.py",
    "application/ports/external_identity_login_synchronizer.py",
    "application/ports/external_identity_verifier.py",
    "application/ports/notification_settings_initializer.py",
    "application/ports/token_issuer.py",
    "application/ports/user_provisioner.py",
    "infrastructure/persistence/orm.py",
    "infrastructure/persistence/mapper.py",
    "infrastructure/persistence/credential_repository.py",
    "infrastructure/persistence/external_identity_login_synchronizer.py",
    "infrastructure/identity_providers/firebase.py",
    "infrastructure/tokens/jwt.py",
    "infrastructure/tokens/opaque_refresh_token.py",
}

FORBIDDEN_AUTH_FILES = {
    "api/auth_scheme.py",
    "application/constants.py",
    "application/principal.py",
    "application/queries/current_principal/result.py",
    "application/security/__init__.py",
    "application/security/messages.py",
    "application/security/principal.py",
    "application/authorize/use_case.py",
    "application/login/schemas.py",
    "application/login/use_case.py",
    "application/refresh/schemas.py",
    "application/refresh/use_case.py",
    "application/logout/schemas.py",
    "application/logout/use_case.py",
    "application/withdraw/schemas.py",
    "application/withdraw/use_case.py",
    "application/ports/access_token.py",
    "application/ports/refresh_token_generator.py",
    "infrastructure/persistence/repository.py",
    "infrastructure/tokens/refresh_token.py",
}

FORBIDDEN_APPLICATION_IMPORT_PREFIXES = (
    "app.modules.auth.infrastructure",
    ".".join(("app", "modules", "users", "infrastructure")),
    "firebase_admin",
    "jwt",
    "sqlalchemy",
)

FORBIDDEN_AUTH_ROUTE_FRAGMENTS = (
    "/logout-all",
    "logout_all",
    "/users",
    "users/me",
    "push-tokens",
)


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


def _class_field_names(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        statement.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == class_name
        for statement in node.body
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
    }


def test_auth_file_structure_matches_hexagonal_completion_goal() -> None:
    missing_files = [
        relative_path
        for relative_path in EXPECTED_AUTH_FILES
        if not (AUTH_ROOT / relative_path).is_file()
    ]
    forbidden_files = [
        relative_path
        for relative_path in FORBIDDEN_AUTH_FILES
        if (AUTH_ROOT / relative_path).exists()
    ]

    assert missing_files == []
    assert forbidden_files == []


def test_auth_application_flow_classes_use_command_query_use_case_names() -> None:
    forbidden_class_names = {
        "Authorize" + "UseCase",
        "Login" + "UseCase",
        "Logout" + "UseCase",
        "RefreshToken" + "UseCase",
        "WithdrawAccount" + "UseCase",
    }
    discovered_forbidden_classes = [
        f"{path.relative_to(PROJECT_ROOT).as_posix()}::{node.name}"
        for path in APPLICATION_ROOT.rglob("*.py")
        if "tests" not in path.parts
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.ClassDef) and node.name in forbidden_class_names
    ]

    assert discovered_forbidden_classes == []


def test_auth_domain_models_use_core_entity_base() -> None:
    assert all(
        issubclass(model, Entity) for model in (UserCredential, ExternalIdentity, RefreshToken)
    )


def test_auth_domain_does_not_import_persistence_frameworks() -> None:
    assert _imports(AUTH_ROOT / "domain" / "model.py").isdisjoint(
        {"sqlalchemy", "sqlalchemy.orm", "sqlalchemy.dialects.postgresql", "app.core.db.base"}
    )


def test_auth_application_does_not_import_infrastructure() -> None:
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in APPLICATION_ROOT.rglob("*.py")
        if "tests" not in path.parts
        and any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in _imports(path)
            for forbidden in FORBIDDEN_APPLICATION_IMPORT_PREFIXES
        )
    ]

    assert offending_files == []


def test_auth_guidance_delegates_public_users_api_to_users_bc() -> None:
    guidance = AUTH_GUIDANCE.read_text()

    assert "users profile API" not in guidance
    assert "users public API belongs to the users BC" in guidance
    assert "Do not mount users endpoints in the auth router" in guidance


def test_auth_router_does_not_expose_logout_all_or_users_api() -> None:
    router_source = AUTH_ROUTER.read_text()
    forbidden_fragments = [
        fragment for fragment in FORBIDDEN_AUTH_ROUTE_FRAGMENTS if fragment in router_source
    ]

    assert forbidden_fragments == []


def test_auth_module_does_not_import_users_infrastructure() -> None:
    forbidden_prefix = ".".join(("app", "modules", "users", "infrastructure"))
    offending_files = [
        path
        for path in AUTH_ROOT.rglob("*.py")
        if "tests" not in path.parts
        and any(imported.startswith(forbidden_prefix) for imported in _imports(path))
    ]

    assert offending_files == []


def test_auth_guidance_forbids_noop_cleanup_completion_claim() -> None:
    guidance = AUTH_GUIDANCE.read_text()

    assert "NoOpPushCleanup" in guidance
    assert "must not be used to claim PRD-complete withdrawal cleanup" in guidance


def test_runtime_wiring_uses_module_dependencies_not_app_composition() -> None:
    main_imports = _imports(PROJECT_ROOT / "app" / "main.py")

    assert not (PROJECT_ROOT / "app" / "composition").exists()
    assert all(not imported.startswith("app.composition") for imported in main_imports)


def test_token_port_contract_is_provider_neutral() -> None:
    port_file = AUTH_ROOT / "application" / "ports" / "token_issuer.py"

    assert _imports(port_file).isdisjoint(
        {
            "PyJWT",
            "app.modules.auth.infrastructure.tokens.jwt",
            "app.modules.auth.infrastructure.tokens.opaque_refresh_token",
            "jwt",
        }
    )

    token_issuer = importlib.import_module("app.modules.auth.application.ports.token_issuer")
    assert {
        "AccessTokenIssuer",
        "AccessTokenVerifier",
        "RefreshTokenIssuer",
        "RefreshTokenHasher",
        "IssuedAccessToken",
        "IssuedRefreshToken",
    }.issubset(vars(token_issuer))


def test_command_results_do_not_own_http_token_type() -> None:
    assert "token_type" not in _class_field_names(
        AUTH_ROOT / "application" / "commands" / "login" / "result.py", "LoginResult"
    )
    assert "token_type" not in _class_field_names(
        AUTH_ROOT / "application" / "commands" / "refresh" / "result.py",
        "RefreshTokenResult",
    )


def test_token_principal_model_is_owned_by_core_security() -> None:
    principal_module = importlib.import_module("app.core.security.principal")
    forbidden_imports = {
        "app.modules.auth.application.authorize" + ".schemas",
        "app.modules.auth.application" + ".principal",
        "app.modules.auth.application.queries.current_principal" + ".result",
        "app.modules.auth.application" + ".security",
    }
    guarded_files = (
        AUTH_ROOT / "application" / "ports" / "token_issuer.py",
        AUTH_ROOT / "application" / "queries" / "current_principal" / "use_case.py",
        AUTH_ROOT / "infrastructure" / "tokens" / "jwt.py",
        AUTH_ROOT / "api" / "security.py",
    )

    offending_imports = [
        f"{path.relative_to(PROJECT_ROOT).as_posix()} imports {forbidden_import}"
        for path in guarded_files
        for forbidden_import in forbidden_imports
        if forbidden_import in _imports(path)
    ]

    assert hasattr(principal_module, "AuthenticatedPrincipal")
    assert offending_imports == [], (
        "AuthenticatedPrincipal must be owned by "
        "app.core.security.principal; "
        f"violations: {offending_imports}"
    )
