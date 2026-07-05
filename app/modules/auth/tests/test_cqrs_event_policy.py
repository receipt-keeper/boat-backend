from pathlib import Path
from typing import Final

PROJECT_ROOT = Path(__file__).resolve().parents[4]
AUTH_ROOT = PROJECT_ROOT / "app" / "modules" / "auth"
USERS_ROOT = PROJECT_ROOT / "app" / "modules" / "users"
APPLICATION_ROOT = AUTH_ROOT / "application"
AUTH_ROUTER = AUTH_ROOT / "api" / "router.py"
AUTH_GUIDANCE = AUTH_ROOT / "AGENTS.md"
USERS_GUIDANCE = USERS_ROOT / "AGENTS.md"
ROOT_ARCHITECTURE = PROJECT_ROOT / "ARCHITECTURE.md"

EXPECTED_AUTH_COMMAND_QUERY_FILES = {
    "application/commands/login/command.py",
    "application/commands/login/result.py",
    "application/commands/login/use_case.py",
    "application/commands/refresh/command.py",
    "application/commands/refresh/result.py",
    "application/commands/refresh/use_case.py",
    "application/commands/logout/command.py",
    "application/commands/logout/use_case.py",
    "application/commands/withdraw/command.py",
    "application/commands/withdraw/use_case.py",
    "application/queries/current_principal/query.py",
    "application/queries/current_principal/use_case.py",
}
FORBIDDEN_AUTH_APPLICATION_FILES = {
    "application/authorize/use_case.py",
    "application/login/schemas.py",
    "application/login/use_case.py",
    "application/refresh/schemas.py",
    "application/refresh/use_case.py",
    "application/logout/schemas.py",
    "application/logout/use_case.py",
    "application/withdraw/schemas.py",
    "application/withdraw/use_case.py",
}
READ_MODEL_PACKAGE_NAMES = ("read_models",)
# ("out", "box") 항목은 이 목록에서 제거되었다. transactional outbox는 CLAUDE.md
# ANTI-PATTERNS에서 승인된 패턴이기 때문이다 — "transactional outbox는
# `app/core/db/outbox`(ORM·직렬화·publisher·relay)로 도입되었다 — 목적지는 in-process
# `EventDispatcher`뿐이며 외부 message bus/Kafka 연동은 여전히 금지다."
# 승인 범위 밖의 자체 outbox 구현은 아래
# test_outbox_references_go_through_approved_core_outbox_module이 계속 금지한다.
GUARDED_TERM_FRAGMENTS: Final[tuple[tuple[str, ...], ...]] = (
    ("command", " ", "bus"),
    ("query", " ", "bus"),
    ("event", " ", "sourcing"),
    ("external", " ", "message", " ", "bus"),
    ("ka", "fka"),
    ("rab", "bit", "mq"),
    ("cel", "ery"),
    ("dra", "matiq"),
    ("event", "_", "store"),
    ("event", " ", "store"),
    ("read", " ", "db"),
    ("read", " ", "database"),
    ("read", "-", "store"),
    ("read", "_", "store"),
    ("read", " ", "store"),
    ("projection", " ", "worker"),
    ("material", "ized"),
)


def _python_source_files() -> list[Path]:
    return [
        path
        for module_root in (AUTH_ROOT, USERS_ROOT)
        for path in module_root.rglob("*.py")
        if "tests" not in path.relative_to(module_root).parts
    ]


def _guarded_terms() -> tuple[str, ...]:
    return tuple("".join(fragments) for fragments in GUARDED_TERM_FRAGMENTS)


def _has_public_auth_read_endpoint() -> bool:
    router_source = AUTH_ROUTER.read_text()
    return "@router.get" in router_source or "@router.head" in router_source


def _documents_public_read_model_policy() -> bool:
    guidance = AUTH_GUIDANCE.read_text()
    architecture = ROOT_ARCHITECTURE.read_text()
    policy_text = f"{guidance}\n{architecture}"
    return all(term in policy_text for term in ("public read API", "read model"))


def test_auth_application_flow_packages_expose_command_query_roles() -> None:
    missing_files = [
        relative_path
        for relative_path in EXPECTED_AUTH_COMMAND_QUERY_FILES
        if not (AUTH_ROOT / relative_path).is_file()
    ]
    forbidden_files = [
        relative_path
        for relative_path in FORBIDDEN_AUTH_APPLICATION_FILES
        if (AUTH_ROOT / relative_path).exists()
    ]

    assert missing_files == []
    assert forbidden_files == []


def test_auth_read_model_packages_require_public_read_surface_and_docs() -> None:
    read_model_directories = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for package_name in READ_MODEL_PACKAGE_NAMES
        for path in APPLICATION_ROOT.rglob(package_name)
        if path.is_dir()
    ]

    if read_model_directories == []:
        return

    assert _has_public_auth_read_endpoint()
    assert _documents_public_read_model_policy(), read_model_directories


def test_auth_source_does_not_use_external_event_or_read_infrastructure() -> None:
    guarded_terms = _guarded_terms()
    offending_files = [
        f"{path.relative_to(PROJECT_ROOT).as_posix()} contains {term}"
        for path in _python_source_files()
        for term in guarded_terms
        if term in path.read_text().lower()
    ]

    assert offending_files == []


def test_outbox_references_go_through_approved_core_outbox_module() -> None:
    """outbox 참조는 승인된 core 모듈 경유만 허용한다.

    CLAUDE.md ANTI-PATTERNS: "transactional outbox는 `app/core/db/outbox`(ORM·직렬화·
    publisher·relay)로 도입되었다 — 목적지는 in-process `EventDispatcher`뿐이며 외부
    message bus/Kafka 연동은 여전히 금지다." 따라서 auth/users 소스가 outbox를 언급하는
    파일은 반드시 승인된 `app.core.db.outbox`를 import해야 하며, 모듈 자체의 outbox
    구현(별도 outbox 테이블/relay/publisher 정의)은 금지한다.
    """
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in _python_source_files()
        if "outbox" in path.read_text().lower() and "app.core.db.outbox" not in path.read_text()
    ]

    assert offending_files == []


def test_prd_guidance_reopens_users_public_api_scope_in_users_bc() -> None:
    users_guidance = USERS_GUIDANCE.read_text()
    auth_guidance = AUTH_GUIDANCE.read_text()

    assert "Users public API scope is reopened for this PRD" in users_guidance
    assert "users public API belongs to the users BC" in auth_guidance
    assert "Do not mount users endpoints in the auth router" in auth_guidance


def test_prd_guidance_forbids_noop_withdrawal_completion_claim() -> None:
    auth_guidance = AUTH_GUIDANCE.read_text()

    assert "NoOpPushCleanup cannot satisfy PRD-complete withdrawal" in auth_guidance
    assert "missing BC cleanup must remain unclaimed" in auth_guidance
