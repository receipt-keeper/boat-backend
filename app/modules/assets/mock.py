from dataclasses import replace
from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.modules.assets.domain import Asset, EvidenceType

SAMPLE_ASSETS: Final[tuple[Asset, ...]] = (
    Asset(
        asset_id=UUID("00000000-0000-0000-0000-000000000501"),
        product_name="삼성 냉장고 875L",
        brand_name="삼성",
        category="주방 가전",
        image_url="/api/v1/files/00000000-0000-0000-0000-000000000201/content",
        purchase_location="전자랜드",
        purchase_date=date(2024, 5, 26),
        warranty_period_months=24,
        warranty_expires_on=date(2026, 7, 10),
        warranty_d_day=14,
        memo="주방 냉장고",
        total_amount=5137000,
        serial_number="SN-20240526-001",
        receipt_file_ids=(UUID("00000000-0000-0000-0000-000000000201"),),
        support_url="https://www.samsungsvc.co.kr",
        registered_at=datetime(2026, 6, 12, 9, 0),
        evidence_type=EvidenceType.RECEIPT,
        evidence_id=UUID("00000000-0000-0000-0000-000000000301"),
    ),
    Asset(
        asset_id=UUID("00000000-0000-0000-0000-000000000502"),
        product_name="LG 세탁기",
        brand_name="LG",
        category="세탁/청소",
        image_url="/api/v1/files/00000000-0000-0000-0000-000000000202/content",
        purchase_location="하이마트",
        purchase_date=date(2025, 1, 5),
        warranty_period_months=12,
        warranty_expires_on=date(2026, 6, 20),
        warranty_d_day=-6,
        memo=None,
        total_amount=1290000,
        serial_number=None,
        receipt_file_ids=(UUID("00000000-0000-0000-0000-000000000202"),),
        support_url="https://www.lge.co.kr/support",
        registered_at=datetime(2026, 6, 10, 14, 30),
        evidence_type=EvidenceType.RECEIPT,
        evidence_id=UUID("00000000-0000-0000-0000-000000000302"),
    ),
    Asset(
        asset_id=UUID("00000000-0000-0000-0000-000000000503"),
        product_name="다이슨 청소기",
        brand_name="Dyson",
        category="세탁/청소",
        image_url="/api/v1/files/00000000-0000-0000-0000-000000000203/content",
        purchase_location="코스트코",
        purchase_date=date(2026, 3, 2),
        warranty_period_months=24,
        warranty_expires_on=date(2028, 3, 2),
        warranty_d_day=615,
        memo="거실 청소용",
        total_amount=890000,
        serial_number=None,
        receipt_file_ids=(UUID("00000000-0000-0000-0000-000000000203"),),
        support_url="https://www.dyson.co.kr/support",
        registered_at=datetime(2026, 6, 8, 11, 15),
        evidence_type=EvidenceType.RECEIPT,
        evidence_id=UUID("00000000-0000-0000-0000-000000000303"),
    ),
)


def asset_with_id(asset_id: UUID) -> Asset:
    for asset in SAMPLE_ASSETS:
        if asset.asset_id == asset_id:
            return asset
    return replace(SAMPLE_ASSETS[0], asset_id=asset_id)
