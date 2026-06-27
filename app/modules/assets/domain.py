from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID


class AssetStatusFilter(StrEnum):
    ALL = "all"
    EXPIRING = "expiring"
    EXPIRED = "expired"


class AssetSort(StrEnum):
    RECENT = "recent"
    EXPIRES_ON = "expiresOn"


class EvidenceType(StrEnum):
    RECEIPT = "receipt"


@dataclass(frozen=True, slots=True)
class Asset:
    asset_id: UUID
    product_name: str
    brand_name: str | None
    category: str | None
    image_url: str | None
    purchase_location: str | None
    purchase_date: date
    warranty_period_months: int
    warranty_expires_on: date
    warranty_d_day: int
    memo: str | None
    total_amount: int | None
    serial_number: str | None
    receipt_file_ids: tuple[UUID, ...]
    support_url: str | None
    registered_at: datetime
    evidence_type: EvidenceType
    evidence_id: UUID
