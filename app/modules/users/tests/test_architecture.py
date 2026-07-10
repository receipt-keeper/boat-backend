import ast
import dataclasses
from pathlib import Path

from app.core.config.settings import Settings
from app.core.domain.entity import AggregateRoot, Entity
from app.core.domain.events import DomainEvent
from app.main import create_app
from app.modules.users.application.ports.user_repository import UserNotificationCandidate
from app.modules.users.domain import events as users_events
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
    "domain/events.py",
}

EXPECTED_USERS_EVENT_CLASSES = {
    "UserRegistered",
    "UserProfileImageChanged",
    "UserWithdrawn",
}

FORBIDDEN_USERS_FILES = {
    "application/provision/schemas.py",
    "application/provision/use_case.py",
    "application/delete/schemas.py",
    "application/delete/use_case.py",
}

PRD_USERS_PUBLIC_ENDPOINTS = (
    "GET /api/v1/users/me",
    "DELETE /api/v1/users/me",
)

RETIRED_USERS_PUBLIC_ENDPOINTS = (
    "PATCH /api/v1/users/me",
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
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def test_users_domain_model_uses_core_entity_base() -> None:
    assert issubclass(User, Entity)


def test_user_is_an_aggregate_root() -> None:
    assert issubclass(User, AggregateRoot)


def test_users_domain_events_module_declares_expected_event_classes() -> None:
    declared = {
        name
        for name in dir(users_events)
        if isinstance(getattr(users_events, name), type)
        and issubclass(getattr(users_events, name), DomainEvent)
        and getattr(users_events, name) is not DomainEvent
    }

    assert declared == EXPECTED_USERS_EVENT_CLASSES


def test_users_domain_events_are_frozen_kw_only_dataclasses() -> None:
    for name in EXPECTED_USERS_EVENT_CLASSES:
        event_class = getattr(users_events, name)
        params = event_class.__dict__["__dataclass_params__"]

        assert params.frozen is True
        assert params.kw_only is True


def test_users_domain_events_only_use_serializable_payload_types() -> None:
    # outbox serialization이 지원하는 UUID/datetime/StrEnum/기본형만 허용한다
    # (app/core/db/outbox/serialization.py:38-64).
    allowed_annotation_fragments = ("UUID", "str", "int", "float", "bool", "None", "datetime")
    offending_fields = [
        f"{event_class.__name__}.{field.name}"
        for name in EXPECTED_USERS_EVENT_CLASSES
        for event_class in (getattr(users_events, name),)
        for field in dataclasses.fields(event_class)
        if field.name not in {"event_id", "occurred_at", "event_version"}
        and not any(fragment in str(field.type) for fragment in allowed_annotation_fragments)
    ]

    assert offending_fields == []


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
    assert "Users owns the PRD public mypage profile scope" in guidance
    assert all(endpoint in guidance for endpoint in PRD_USERS_PUBLIC_ENDPOINTS)
    assert all(endpoint not in guidance for endpoint in RETIRED_USERS_PUBLIC_ENDPOINTS)


def test_users_openapi_exposes_only_app_public_contract() -> None:
    schema = create_app(OPENAPI_TEST_SETTINGS).openapi()
    paths = schema["paths"]
    components = schema["components"]["schemas"]

    me_operations = paths["/api/v1/users/me"]
    assert {"get", "delete"}.issubset(set(me_operations))
    assert "patch" not in me_operations

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


def test_user_notification_candidate_exposes_only_policy_neutral_fields() -> None:
    field_names = {field.name for field in dataclasses.fields(UserNotificationCandidate)}

    assert field_names == {
        "user_id",
        "created_at",
        "days_since_joined",
        "cursor_created_at",
        "cursor_id",
    }
    assert "join_based_bucket" not in field_names
    assert all(not field_name.startswith("join_day_") for field_name in field_names)


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


def test_users_application_and_domain_do_not_import_files_infrastructure() -> None:
    forbidden_files_prefixes = ("app.modules.files.infrastructure",)
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for root in (USERS_ROOT / "application", USERS_ROOT / "domain")
        for path in root.rglob("*.py")
        if "tests" not in path.parts
        and any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for imported in _imports(path)
            for prefix in forbidden_files_prefixes
        )
    ]

    assert offending_files == []
