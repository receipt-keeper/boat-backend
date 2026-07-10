import ast
from pathlib import Path

_RECEIPTS_ROOT = Path(__file__).parents[1]
_RECEIPT_REPOSITORY = _RECEIPTS_ROOT / "application" / "ports" / "receipt_repository.py"
_QUERY_PATHS = (
    _RECEIPTS_ROOT / "application" / "queries" / "list_receipts_expiring_on" / "query.py",
    _RECEIPTS_ROOT / "application" / "queries" / "get_receipt_activity_for_users" / "query.py",
)
_LEGACY_SCHEDULER_SYMBOLS = (
    "WarrantyNotificationCandidate",
    "ReceiptRegistrationActivity",
    "list_warranty_notification_candidates",
    "list_receipt_registration_activity_candidates",
)


def test_receipt_repository_excludes_scheduler_read_contracts() -> None:
    repository_source = _RECEIPT_REPOSITORY.read_text()

    assert all(symbol not in repository_source for symbol in _LEGACY_SCHEDULER_SYMBOLS)


def test_receipts_module_has_no_stale_scheduler_read_contract_imports() -> None:
    production_paths = (
        *(_RECEIPTS_ROOT / "application").rglob("*.py"),
        *(_RECEIPTS_ROOT / "infrastructure").rglob("*.py"),
        _RECEIPTS_ROOT / "dependencies.py",
    )
    offending_files = [
        path.relative_to(_RECEIPTS_ROOT).as_posix()
        for path in production_paths
        if any(symbol in path.read_text() for symbol in _LEGACY_SCHEDULER_SYMBOLS)
    ]

    assert offending_files == []


def test_scheduler_facing_query_contracts_do_not_raise_bare_value_error() -> None:
    for query_path in _QUERY_PATHS:
        tree = ast.parse(query_path.read_text())
        assert not any(
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "ValueError"
            for node in ast.walk(tree)
        )
