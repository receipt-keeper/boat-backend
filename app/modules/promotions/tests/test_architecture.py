import ast
from pathlib import Path

from app.core.config.settings import Settings
from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PROMOTIONS_ROOT = PROJECT_ROOT / "app" / "modules" / "promotions"
CREDITS_ROOT = PROJECT_ROOT / "app" / "modules" / "credits"
TEST_SETTINGS = Settings(app_name="Boat Backend")

EXPECTED_LAYOUT_FILES = {
    "api/router.py",
    "api/schemas.py",
    "application/commands/create_promotion_code_redemption/command.py",
    "application/commands/create_promotion_code_redemption/use_case.py",
    "application/commands/create_promotion_redemption/command.py",
    "application/commands/create_promotion_redemption/result.py",
    "application/commands/create_promotion_redemption/use_case.py",
    "application/ports/credit_grant.py",
    "application/ports/promotion_repository.py",
    "application/queries/get_current_ocr_credit_promotion/query.py",
    "application/queries/get_current_ocr_credit_promotion/result.py",
    "application/queries/get_current_ocr_credit_promotion/use_case.py",
    "dependencies.py",
    "domain/exceptions.py",
    "domain/model.py",
    "infrastructure/persistence/mapper.py",
    "infrastructure/persistence/orm.py",
    "infrastructure/persistence/repository.py",
}
FORBIDDEN_FLAT_FILES = {
    "application/service.py",
    "domain.py",
    "infrastructure/repository.py",
}
FORBIDDEN_APPLICATION_DOMAIN_IMPORT_PREFIXES = (
    "app.modules.credits.infrastructure",
    "app.modules.users.infrastructure",
    "fastapi",
    "sqlalchemy",
    "app.core.db",
    "firebase_admin",
    "google.cloud",
    "openai",
    "anthropic",
    "boto3",
    "httpx",
    "httpx2",
    "requests",
)
FORBIDDEN_RELATIVE_IMPORT_PREFIXES = ("infrastructure",)
FORBIDDEN_PRODUCTION_SCHEMA_API_TERMS = (
    "credit_grants",
    "credit_accounts",
    "promotion_contents",
    "event_offers",
    "event_redemptions",
    "event_campaigns",
    "title",
    "body",
    "cta_label",
    "ctalabel",
    "image_url",
    "imageurl",
    "surface",
    "banner",
    "outbox",
    "broker",
    "scheduler",
    "event sourcing",
    "event_sourcing",
    "message_bus",
    "event_bus",
    "kafka",
    "rabbitmq",
    "celery",
)
EXPECTED_PROMOTION_PUBLIC_PATHS = {
    "/api/v1/promotions",
    "/api/v1/promotions/redemptions",
    "/api/v1/promotions/{promotion_id}/redemptions",
}
EXPECTED_CREDIT_TRANSACTION_FIELDS = {
    "reason",
    "action",
    "amount",
    "createdAt",
}
FORBIDDEN_CREDIT_TRANSACTION_FIELDS = {
    "sourceType",
    "sourceId",
    "idempotencyKey",
    "promotionId",
    "promotionRedemptionId",
}


def test_promotions_module_uses_pinned_vertical_slice_layout() -> None:
    missing_files = [
        relative_path
        for relative_path in EXPECTED_LAYOUT_FILES
        if not (PROMOTIONS_ROOT / relative_path).is_file()
    ]
    forbidden_files = [
        relative_path
        for relative_path in FORBIDDEN_FLAT_FILES
        if (PROMOTIONS_ROOT / relative_path).exists()
    ]

    assert {"missing": missing_files, "forbidden": forbidden_files} == {
        "missing": [],
        "forbidden": [],
    }


def test_promotions_application_and_domain_stay_adapter_free() -> None:
    offending_imports = {
        path.relative_to(PROJECT_ROOT).as_posix(): sorted(
            imported
            for imported in _imports(path)
            if _imports_forbidden_prefix(
                imported,
                FORBIDDEN_APPLICATION_DOMAIN_IMPORT_PREFIXES,
            )
            or _relative_imports_forbidden_prefix(
                imported,
                FORBIDDEN_RELATIVE_IMPORT_PREFIXES,
            )
        )
        for root in (PROMOTIONS_ROOT / "application", PROMOTIONS_ROOT / "domain")
        for path in root.rglob("*.py")
        if "tests" not in path.parts
    }

    assert {path: imports for path, imports in offending_imports.items() if imports} == {}


def test_promotion_codes_are_internal_table_not_public_resource() -> None:
    orm_source = (PROMOTIONS_ROOT / "infrastructure" / "persistence" / "orm.py").read_text(
        encoding="utf-8"
    )
    api_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in (PROMOTIONS_ROOT / "api").rglob("*.py")
    )

    assert '__tablename__ = "promotion_codes"' in orm_source
    assert "/promotion-codes" not in api_sources


def test_production_schema_and_api_exclude_forbidden_promotion_credit_concepts() -> None:
    offending_terms = {
        path.relative_to(PROJECT_ROOT).as_posix(): sorted(
            term
            for term in FORBIDDEN_PRODUCTION_SCHEMA_API_TERMS
            if term in path.read_text(encoding="utf-8").casefold()
        )
        for path in _production_schema_api_sources()
    }

    assert {path: terms for path, terms in offending_terms.items() if terms} == {}


def test_promotions_public_openapi_paths_are_exact() -> None:
    schema = create_app(TEST_SETTINGS).openapi()
    paths = schema["paths"]
    promotion_paths = {
        path
        for path in paths
        if path.startswith("/api/v1/promotions") or path.startswith("/api/v1/promotion-codes")
    }

    assert promotion_paths == EXPECTED_PROMOTION_PUBLIC_PATHS
    assert set(paths["/api/v1/promotions"]) == {"get"}
    assert set(paths["/api/v1/promotions/redemptions"]) == {"post"}
    assert set(paths["/api/v1/promotions/{promotion_id}/redemptions"]) == {"post"}


def test_credit_transaction_public_schema_exposes_existing_fields_only() -> None:
    schema = create_app(TEST_SETTINGS).openapi()
    components = schema["components"]
    assert isinstance(components, dict)
    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    transaction_schema = schemas["CreditTransactionResponse"]
    assert isinstance(transaction_schema, dict)
    properties = transaction_schema["properties"]
    assert isinstance(properties, dict)
    public_fields = set(properties)

    assert public_fields == EXPECTED_CREDIT_TRANSACTION_FIELDS
    assert public_fields.isdisjoint(FORBIDDEN_CREDIT_TRANSACTION_FIELDS)


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


def _production_schema_api_sources() -> list[Path]:
    module_sources = [
        path
        for root in (
            PROMOTIONS_ROOT / "api",
            PROMOTIONS_ROOT / "infrastructure" / "persistence",
            CREDITS_ROOT / "api",
            CREDITS_ROOT / "infrastructure" / "persistence" / "orm.py",
        )
        for path in _python_sources(root)
    ]
    migration_sources = [
        path
        for path in (PROJECT_ROOT / "alembic" / "versions").glob("*.py")
        if _is_promotion_credit_migration(path)
    ]
    return module_sources + migration_sources


def _python_sources(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return [
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and "tests" not in path.parts
    ]


def _is_promotion_credit_migration(path: Path) -> bool:
    source = path.read_text(encoding="utf-8").casefold()
    return "promotion" in source or "credit" in source
