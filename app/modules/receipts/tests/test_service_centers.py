from urllib.parse import parse_qs, urlparse

import pytest

from app.modules.receipts.domain.service_centers import resolve_service_center_url


@pytest.mark.parametrize(
    ("brand_name", "expected_url"),
    [
        ("삼성", "https://www.samsungsvc.co.kr"),
        ("LG전자", "https://www.lge.co.kr/support"),
        ("Apple", "https://support.apple.com/ko-kr/repair"),
        ("소니", "https://www.sony.co.kr/electronics/support"),
        ("Dyson", "https://www.dyson.co.kr/support"),
    ],
)
def test_resolve_service_center_url_uses_official_brand_link(
    brand_name: str,
    expected_url: str,
) -> None:
    assert (
        resolve_service_center_url(brand_name=brand_name, item_name="무선 청소기") == expected_url
    )


def test_resolve_service_center_url_uses_item_name_when_brand_is_missing() -> None:
    assert (
        resolve_service_center_url(brand_name=None, item_name="삼성 냉장고 875L")
        == "https://www.samsungsvc.co.kr"
    )


def test_resolve_service_center_url_falls_back_to_brand_search() -> None:
    url = resolve_service_center_url(brand_name="보트전자", item_name="전기포트")

    assert url.startswith("https://search.naver.com/search.naver")
    assert _fallback_query(url) == "보트전자 서비스센터"


def test_resolve_service_center_url_falls_back_to_item_search_when_brand_is_missing() -> None:
    url = resolve_service_center_url(brand_name=None, item_name="무선 제습기")

    assert url.startswith("https://search.naver.com/search.naver")
    assert _fallback_query(url) == "무선 제습기 서비스센터"


def _fallback_query(url: str) -> str:
    parsed = urlparse(url)
    return parse_qs(parsed.query)["query"][0]
