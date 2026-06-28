from datetime import date, datetime, timedelta
from uuid import UUID

from app.modules.receipts.application.read_models.receipt import ReceiptReadModel
from app.modules.receipts.domain.value_objects import ReceiptStatusFilter


def test_receipt_read_model_exposes_domain_owned_warranty_status() -> None:
    receipt = _receipt_read_model(
        receipt_id=UUID("00000000-0000-0000-0000-000000000301"),
        item_name="만료 임박 영수증",
        registered_at=datetime(2026, 6, 10, 9, 0),
        expires_on=date.today() + timedelta(days=10),
    )

    assert receipt.warranty_d_day == 10
    assert receipt.warranty_status == ReceiptStatusFilter.EXPIRING


def _receipt_read_model(
    *,
    receipt_id: UUID,
    item_name: str,
    registered_at: datetime,
    expires_on: date,
) -> ReceiptReadModel:
    return ReceiptReadModel(
        receipt_id=receipt_id,
        user_id=UUID("00000000-0000-0000-0000-000000000101"),
        item_name=item_name,
        brand_name=None,
        payment_location=None,
        payment_date=date(2024, 5, 26),
        total_amount=None,
        period_months=12,
        expires_on=expires_on,
        category=None,
        memo=None,
        requires_physical_receipt=False,
        receipt_file_ids=(UUID("00000000-0000-0000-0000-000000000201"),),
        registered_at=registered_at,
    )
