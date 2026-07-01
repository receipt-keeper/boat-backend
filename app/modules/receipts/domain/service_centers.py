from urllib.parse import quote_plus


def resolve_service_center_url(*, brand_name: str | None, item_name: str) -> str:
    """Return a service-center search URL based on brand first, then item name."""

    keyword = _search_keyword(brand_name=brand_name, item_name=item_name)
    query = quote_plus(f"{keyword} 서비스센터")
    return f"https://search.naver.com/search.naver?query={query}"


def _search_keyword(*, brand_name: str | None, item_name: str) -> str:
    stripped_brand_name = _blank_to_none(brand_name)
    if stripped_brand_name is not None:
        return stripped_brand_name

    return item_name.strip()


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None
