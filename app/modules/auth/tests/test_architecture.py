import ast
import importlib
from inspect import signature
from pathlib import Path

from app.core.domain.entity import Entity
from app.modules.auth.dependencies import (
    AuthTransactionSessionDep,
    get_credential_repository,
    get_external_identity_login_synchronizer,
    get_user_provisioner,
)
from app.modules.auth.domain.model import ExternalIdentity, RefreshToken, UserCredential

PROJECT_ROOT = Path(__file__).resolve().parents[4]
AUTH_ROOT = PROJECT_ROOT / "app" / "modules" / "auth"
APPLICATION_ROOT = AUTH_ROOT / "application"

EXPECTED_AUTH_FILES = {
    "application/principal.py",
    "application/login/schemas.py",
    "application/login/use_case.py",
    "application/refresh/schemas.py",
    "application/refresh/use_case.py",
    "application/logout/schemas.py",
    "application/logout/use_case.py",
    "application/authorize/use_case.py",
    "application/ports/credential_repository.py",
    "application/ports/external_identity_login_synchronizer.py",
    "application/ports/external_identity_verifier.py",
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
    "application/authorize/schemas.py",
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


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


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


def test_auth_domain_models_use_core_entity_base() -> None:
    assert issubclass(UserCredential, Entity)
    assert issubclass(ExternalIdentity, Entity)
    assert issubclass(RefreshToken, Entity)


def test_auth_domain_does_not_import_persistence_frameworks() -> None:
    domain_imports = _imports(AUTH_ROOT / "domain" / "model.py")

    assert "sqlalchemy" not in domain_imports
    assert "sqlalchemy.orm" not in domain_imports
    assert "sqlalchemy.dialects.postgresql" not in domain_imports
    assert "app.core.db.base" not in domain_imports


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


def test_auth_module_does_not_import_users_infrastructure() -> None:
    forbidden_prefix = ".".join(("app", "modules", "users", "infrastructure"))
    offending_files = [
        path
        for path in AUTH_ROOT.rglob("*.py")
        if "tests" not in path.parts
        and any(imported.startswith(forbidden_prefix) for imported in _imports(path))
    ]

    assert offending_files == []


def test_runtime_wiring_uses_module_dependencies_not_app_composition() -> None:
    main_imports = _imports(PROJECT_ROOT / "app" / "main.py")

    assert not (PROJECT_ROOT / "app" / "composition").exists()
    assert all(not imported.startswith("app.composition") for imported in main_imports)


def test_signup_wiring_shares_one_transaction_session() -> None:
    credential_repository_session = (
        signature(get_credential_repository).parameters["session"].annotation
    )
    login_synchronizer_session = (
        signature(get_external_identity_login_synchronizer).parameters["session"].annotation
    )
    user_provisioner_session = signature(get_user_provisioner).parameters["session"].annotation

    assert credential_repository_session == AuthTransactionSessionDep
    assert login_synchronizer_session == AuthTransactionSessionDep
    assert user_provisioner_session == AuthTransactionSessionDep


def test_token_port_contract_is_provider_neutral() -> None:
    port_file = AUTH_ROOT / "application" / "ports" / "token_issuer.py"
    assert port_file.is_file()

    port_imports = _imports(port_file)
    assert "jwt" not in port_imports
    assert "PyJWT" not in port_imports
    assert "app.modules.auth.infrastructure.tokens.jwt" not in port_imports
    assert "app.modules.auth.infrastructure.tokens.opaque_refresh_token" not in port_imports

    token_issuer = importlib.import_module("app.modules.auth.application.ports.token_issuer")
    for name in (
        "AccessTokenIssuer",
        "AccessTokenVerifier",
        "RefreshTokenIssuer",
        "RefreshTokenHasher",
        "IssuedAccessToken",
        "IssuedRefreshToken",
    ):
        assert hasattr(token_issuer, name)


def test_token_principal_model_is_not_owned_by_authorize_use_case() -> None:
    forbidden_import = "app.modules.auth.application.authorize" + ".schemas"
    guarded_files = (
        AUTH_ROOT / "application" / "ports" / "token_issuer.py",
        AUTH_ROOT / "infrastructure" / "tokens" / "jwt.py",
        AUTH_ROOT / "api" / "security.py",
    )

    offending_imports = [
        f"{path.relative_to(PROJECT_ROOT).as_posix()} imports {forbidden_import}"
        for path in guarded_files
        if forbidden_import in _imports(path)
    ]

    assert offending_imports == [], (
        "AuthenticatedPrincipal must be owned by "
        "app.modules.auth.application.principal; "
        f"forbidden imports: {offending_imports}"
    )
