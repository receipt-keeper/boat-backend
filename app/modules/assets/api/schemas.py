from datetime import date, datetime
from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel
from app.modules.assets.domain import Asset, AssetSort, AssetStatusFilter


class AssetListQuery(AppBaseModel):
    model_config = ConfigDict(frozen=True)

    status: AssetStatusFilter = Field(
        default=AssetStatusFilter.ALL,
        description="보증 상태 필터. all은 전체, expiring은 만료 임박, expired는 만료된 자산이다.",
    )
    sort: AssetSort = Field(
        default=AssetSort.RECENT,
        description="정렬 기준. recent는 등록일 내림차순, expiresOn은 보증 만료일 오름차순이다.",
    )
    limit: int = Field(
        default=5,
        description="응답할 최대 자산 수.",
        ge=1,
        le=20,
    )
    category: str | None = Field(
        default=None,
        description="카테고리 완전 일치 필터.",
        min_length=1,
        max_length=100,
    )
    q: str | None = Field(
        default=None,
        description="제품명, 브랜드명, 구매처에서 찾을 검색어.",
        min_length=1,
        max_length=30,
    )


class AssetResponse(AppBaseModel):
    asset_id: UUID = Field(alias="assetId", description="자산 ID.")
    product_name: str = Field(alias="productName", description="제품명.")
    brand_name: str | None = Field(alias="brandName", description="브랜드명.")
    category: str | None = Field(description="대분류 카테고리.")
    image_url: str | None = Field(alias="imageUrl", description="제품 또는 증빙 대표 이미지 URL.")
    purchase_location: str | None = Field(alias="purchaseLocation", description="구매처.")
    purchase_date: date = Field(alias="purchaseDate", description="구매일.")
    warranty_period_months: int = Field(
        alias="warrantyPeriodMonths",
        description="무상 AS 기간.",
    )
    warranty_expires_on: date = Field(alias="warrantyExpiresOn", description="무상 AS 만료일.")
    warranty_d_day: int = Field(
        alias="warrantyDDay",
        description="무상 AS 만료일까지 남은 일수. 만료된 경우 음수.",
    )
    memo: str | None = Field(description="사용자 메모.")
    total_amount: int | None = Field(alias="totalAmount", description="구매 금액.")
    serial_number: str | None = Field(alias="serialNumber", description="시리얼 넘버.")
    receipt_file_ids: list[UUID] = Field(
        alias="receiptFileIds",
        description="상세 화면에 표시할 영수증 이미지 파일 ID 목록.",
    )
    support_url: str | None = Field(alias="supportUrl", description="제조사 고객지원 링크.")
    registered_at: datetime = Field(alias="registeredAt", description="등록 시각.")
    evidence_type: str = Field(alias="evidenceType", description="대표 증빙 유형.")
    evidence_id: UUID = Field(alias="evidenceId", description="대표 증빙 ID.")

    @classmethod
    def from_domain(cls, asset: Asset) -> "AssetResponse":
        return cls(
            assetId=asset.asset_id,
            productName=asset.product_name,
            brandName=asset.brand_name,
            category=asset.category,
            imageUrl=asset.image_url,
            purchaseLocation=asset.purchase_location,
            purchaseDate=asset.purchase_date,
            warrantyPeriodMonths=asset.warranty_period_months,
            warrantyExpiresOn=asset.warranty_expires_on,
            warrantyDDay=asset.warranty_d_day,
            memo=asset.memo,
            totalAmount=asset.total_amount,
            serialNumber=asset.serial_number,
            receiptFileIds=list(asset.receipt_file_ids),
            supportUrl=asset.support_url,
            registeredAt=asset.registered_at,
            evidenceType=asset.evidence_type.value,
            evidenceId=asset.evidence_id,
        )


class AssetListResponse(AppBaseModel):
    assets: list[AssetResponse] = Field(description="자산 목록.")
    total_count: int = Field(alias="totalCount", description="필터 조건에 맞는 전체 자산 수.")
