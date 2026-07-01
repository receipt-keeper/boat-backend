from urllib.parse import parse_qs, urlparse

import pytest

from app.modules.receipts.domain.service_centers import resolve_service_center_url


@pytest.mark.parametrize(
    ("brand_name", "item_name", "expected_query"),
    [
        ("삼성", "냉장고 875L", "삼성 서비스센터"),
        ("LG전자", "세탁기", "LG전자 서비스센터"),
        ("Apple", "아이패드", "Apple 서비스센터"),
        ("보트전자", "전기포트", "보트전자 서비스센터"),
    ],
)
def test_resolve_service_center_url_uses_brand_search_keyword(
    brand_name: str,
    item_name: str,
    expected_query: str,
) -> None:
    url = resolve_service_center_url(brand_name=brand_name, item_name=item_name)

    assert url.startswith("https://search.naver.com/search.naver")
    assert _fallback_query(url) == expected_query


@pytest.mark.parametrize(
    "item_name",
    ["삼성 냉장고 875L", "신형 모델 세탁기", "Bulgari 스마트워치", "Pegasus 노트북"],
)
def test_resolve_service_center_url_uses_item_search_keyword_when_brand_is_missing(
    item_name: str,
) -> None:
    url = resolve_service_center_url(brand_name=None, item_name=item_name)

    assert url.startswith("https://search.naver.com/search.naver")
    assert _fallback_query(url) == f"{item_name} 서비스센터"


def test_resolve_service_center_url_ignores_blank_brand_name() -> None:
    url = resolve_service_center_url(brand_name="   ", item_name="무선 제습기")

    assert _fallback_query(url) == "무선 제습기 서비스센터"


def _fallback_query(url: str) -> str:
    parsed = urlparse(url)
    return parse_qs(parsed.query)["query"][0]
