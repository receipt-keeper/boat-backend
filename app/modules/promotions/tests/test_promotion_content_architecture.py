import re
from pathlib import Path

from app.core.config.settings import Settings
from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PROMOTIONS_ROOT = PROJECT_ROOT / "app" / "modules" / "promotions"
TEST_SETTINGS = Settings(app_name="Boat Backend")

FORBIDDEN_PROMOTION_DISPLAY_TERMS = (
    "title",
    "body",
    "cta_label",
    "ctalabel",
    "surface",
    "placement",
    "priority",
    "metadata",
    "banner_image_file_id",
)
FORBIDDEN_PROMOTION_RESPONSE_FIELDS = {
    "title",
    "body",
    "ctaLabel",
    "surface",
    "placement",
    "priority",
    "metadata",
    "fileId",
}


def test_promotion_production_sources_exclude_display_content_terms() -> None:
    offending_terms = {
        path.relative_to(PROJECT_ROOT).as_posix(): sorted(
            term
            for term in FORBIDDEN_PROMOTION_DISPLAY_TERMS
            if term in path.read_text(encoding="utf-8").casefold()
        )
        for path in _promotion_content_boundary_sources()
    }

    assert {path: terms for path, terms in offending_terms.items() if terms} == {}


def test_promotion_persistence_uses_banner_image_url_not_generic_image_url() -> None:
    generic_image_url_pattern = re.compile(r"(?<!banner_)image_url")
    offending_sources = {
        path.relative_to(PROJECT_ROOT).as_posix(): generic_image_url_pattern.findall(
            path.read_text(encoding="utf-8").casefold()
        )
        for path in _promotion_content_persistence_sources()
    }

    assert {path: terms for path, terms in offending_sources.items() if terms} == {}


def test_promotion_schema_and_api_allow_only_banner_image_content() -> None:
    schemas = _openapi_schemas()
    promotion_properties = _schema_properties(schemas, "PromotionResponse")
    banner_properties = _schema_properties(schemas, "PromotionBannerImageResponse")

    assert promotion_properties == {
        "state",
        "promotionId",
        "benefit",
        "redemption",
        "balance",
        "bannerImage",
    }
    assert "imageUrl" not in promotion_properties
    assert banner_properties == {"imageUrl"}
    assert FORBIDDEN_PROMOTION_RESPONSE_FIELDS.isdisjoint(promotion_properties)
    assert FORBIDDEN_PROMOTION_RESPONSE_FIELDS.isdisjoint(banner_properties)


def _openapi_schemas() -> dict[str, object]:
    components = create_app(TEST_SETTINGS).openapi()["components"]
    assert isinstance(components, dict)
    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    return schemas


def _schema_properties(schemas: dict[str, object], schema_name: str) -> set[str]:
    schema = schemas[schema_name]
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    return set(properties)


def _promotion_content_persistence_sources() -> list[Path]:
    return [
        *list((PROMOTIONS_ROOT / "infrastructure" / "persistence").rglob("*.py")),
        *[
            path
            for path in (PROJECT_ROOT / "alembic" / "versions").glob("*.py")
            if "promotion_contents" in path.read_text(encoding="utf-8")
        ],
    ]


def _promotion_content_boundary_sources() -> list[Path]:
    return [
        *list((PROMOTIONS_ROOT / "api").rglob("*.py")),
        *_promotion_content_persistence_sources(),
    ]
