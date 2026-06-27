from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.assets.api.schemas import AssetListQuery, AssetListResponse, AssetResponse
from app.modules.assets.domain import Asset, AssetSort, AssetStatusFilter
from app.modules.assets.mock import SAMPLE_ASSETS, asset_with_id

_OpenApiResponse = dict[str, type[CommonResponse[ApiErrorData]] | str]

_ERROR_RESPONSES: dict[int | str, _OpenApiResponse] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": CommonResponse[ApiErrorData],
        "description": "검증 실패 - 요청 형식 오류 또는 도메인 검증 실패",
    },
}

router = APIRouter(
    prefix="/assets",
    tags=["assets"],
    responses=_ERROR_RESPONSES,
)


@router.get(
    "",
    response_model=CommonResponse[AssetListResponse],
    summary="자산 목록 조회",
    description="등록된 제품을 보증 상태, 카테고리, 검색어 조건에 맞춰 반환한다.",
)
async def list_assets(
    query: Annotated[AssetListQuery, Query()],
) -> CommonResponse[AssetListResponse]:
    filtered_assets = _sort_assets(_filter_assets(SAMPLE_ASSETS, query), query.sort)
    assets = filtered_assets[: query.limit]
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=AssetListResponse(
            assets=[AssetResponse.from_domain(asset) for asset in assets],
            totalCount=len(filtered_assets),
        ),
    )


@router.get(
    "/{asset_id}",
    response_model=CommonResponse[AssetResponse],
    summary="자산 상세 조회",
    description="제품의 구매 정보, 무상 AS 만료일, 대표 증빙 정보를 반환한다.",
)
async def get_asset(asset_id: UUID) -> CommonResponse[AssetResponse]:
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=AssetResponse.from_domain(asset_with_id(asset_id)),
    )


def _filter_assets(assets: tuple[Asset, ...], query: AssetListQuery) -> list[Asset]:
    filtered = [asset for asset in assets if _matches_status(asset, query.status)]
    if query.category is not None:
        filtered = [asset for asset in filtered if asset.category == query.category]
    if query.q is not None:
        keyword = query.q.casefold()
        filtered = [asset for asset in filtered if _contains_keyword(asset, keyword)]
    return filtered


def _matches_status(asset: Asset, status_filter: AssetStatusFilter) -> bool:
    match status_filter:
        case AssetStatusFilter.ALL:
            return True
        case AssetStatusFilter.EXPIRING:
            return 0 <= asset.warranty_d_day <= 30
        case AssetStatusFilter.EXPIRED:
            return asset.warranty_d_day < 0


def _contains_keyword(asset: Asset, keyword: str) -> bool:
    searchable_values = (
        asset.product_name,
        asset.brand_name,
        asset.purchase_location,
    )
    return any(value is not None and keyword in value.casefold() for value in searchable_values)


def _sort_assets(assets: list[Asset], sort: AssetSort) -> list[Asset]:
    match sort:
        case AssetSort.RECENT:
            return sorted(assets, key=lambda asset: asset.registered_at, reverse=True)
        case AssetSort.EXPIRES_ON:
            return sorted(assets, key=lambda asset: asset.warranty_expires_on)
