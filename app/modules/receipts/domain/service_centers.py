from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True, slots=True)
class ServiceCenterLink:
    url: str
    aliases: tuple[str, ...]


OFFICIAL_SERVICE_CENTER_LINKS: tuple[ServiceCenterLink, ...] = (
    ServiceCenterLink(
        url="https://www.samsungsvc.co.kr",
        aliases=("samsung", "삼성", "삼성전자"),
    ),
    ServiceCenterLink(
        url="https://www.lge.co.kr/support",
        aliases=("lg", "엘지", "엘지전자", "lg전자"),
    ),
    ServiceCenterLink(
        url="https://support.apple.com/ko-kr/repair",
        aliases=("apple", "애플"),
    ),
    ServiceCenterLink(
        url="https://www.sony.co.kr/electronics/support",
        aliases=("sony", "소니"),
    ),
    ServiceCenterLink(
        url="https://www.dyson.co.kr/support",
        aliases=("dyson", "다이슨"),
    ),
    ServiceCenterLink(
        url="https://www.philips.co.kr/c-w/support-home.html",
        aliases=("philips", "필립스"),
    ),
    ServiceCenterLink(
        url="https://support.lenovo.com/kr/ko",
        aliases=("lenovo", "레노버"),
    ),
    ServiceCenterLink(
        url="https://support.hp.com/kr-ko",
        aliases=("hp", "에이치피"),
    ),
    ServiceCenterLink(
        url="https://www.dell.com/support/home/ko-kr",
        aliases=("dell", "델"),
    ),
    ServiceCenterLink(
        url="https://www.asus.com/kr/support/",
        aliases=("asus", "에이수스", "아수스"),
    ),
)


def resolve_service_center_url(*, brand_name: str | None, item_name: str) -> str:
    """Return an official support URL when known, otherwise a search fallback."""

    brand_text = _normalize(brand_name)
    item_text = _normalize(item_name)

    if brand_text:
        official_url = _find_official_url(brand_text)
        if official_url is not None:
            return official_url

    official_url = _find_official_url(item_text)
    if official_url is not None:
        return official_url

    fallback_keyword = brand_name or item_name
    return _naver_service_center_search_url(fallback_keyword)


def _find_official_url(text: str) -> str | None:
    for service_center in OFFICIAL_SERVICE_CENTER_LINKS:
        if any(_normalize(alias) in text for alias in service_center.aliases):
            return service_center.url
    return None


def _normalize(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.casefold().split())


def _naver_service_center_search_url(keyword: str) -> str:
    query = quote_plus(f"{keyword.strip()} 서비스센터")
    return f"https://search.naver.com/search.naver?query={query}"
