from uuid import UUID

from app.modules.receipts.application.read_models.receipt import ReceiptReadModel
from app.modules.receipts.domain.model import Receipt as DomainReceipt
from app.modules.receipts.infrastructure.persistence import orm


def receipt_to_record(receipt: DomainReceipt) -> orm.Receipt:
    return orm.Receipt(
        id=receipt.id,
        user_id=receipt.user_id,
        item_name=receipt.item_name.value,
        brand_name=receipt.brand_name,
        payment_location=receipt.payment_location,
        payment_date=receipt.payment_date.value,
        total_amount=None if receipt.total_amount is None else receipt.total_amount.value,
        period_months=receipt.period_months.value,
        expires_on=receipt.expires_on,
        category=receipt.category,
        sub_category=receipt.sub_category,
        memo=receipt.memo,
        requires_physical_receipt=receipt.requires_physical_receipt,
    )


def attachment_to_record(*, receipt_id: UUID, file_id: UUID) -> orm.ReceiptAttachment:
    return orm.ReceiptAttachment(receipt_id=receipt_id, file_id=file_id)


def record_to_read_model(
    record: orm.Receipt,
    *,
    receipt_file_ids: tuple[UUID, ...],
) -> ReceiptReadModel:
    return ReceiptReadModel(
        receipt_id=record.id,
        user_id=record.user_id,
        item_name=record.item_name,
        brand_name=record.brand_name,
        payment_location=record.payment_location,
        payment_date=record.payment_date,
        total_amount=record.total_amount,
        period_months=record.period_months,
        expires_on=record.expires_on,
        category=record.category,
        sub_category=record.sub_category,
        memo=record.memo,
        requires_physical_receipt=record.requires_physical_receipt,
        receipt_file_ids=receipt_file_ids,
        registered_at=record.created_at,
    )
