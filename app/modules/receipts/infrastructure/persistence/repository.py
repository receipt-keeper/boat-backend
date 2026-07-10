from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.receipts.infrastructure.persistence.listing as listing
from app.modules.receipts.application.ports.receipt_repository import (
    ReceiptListPage,
    ReceiptRegistrationActivityPage,
    ReceiptRegistrationActivityQuery,
    ReceiptRepository,
    WarrantyNotificationCandidatePage,
    WarrantyNotificationCandidateQuery,
)
from app.modules.receipts.application.queries.list_receipts.query import ListReceiptsQuery
from app.modules.receipts.application.read_models.receipt import ReceiptReadModel
from app.modules.receipts.domain.model import Receipt
from app.modules.receipts.infrastructure.persistence import mapper, orm
from app.modules.receipts.infrastructure.persistence import (
    notification_candidates as candidate_queries,
)


class SqlAlchemyReceiptRepository(ReceiptRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, receipt: Receipt) -> ReceiptReadModel:
        record = mapper.receipt_to_record(receipt)
        self._session.add(record)
        for file_id in receipt.receipt_file_ids:
            self._session.add(mapper.attachment_to_record(receipt_id=receipt.id, file_id=file_id))
        await self._session.flush()
        await self._session.refresh(record)
        return await self._record_to_read_model(record)

    async def list_by_user(self, *, query: ListReceiptsQuery) -> ReceiptListPage:
        conditions = listing.list_conditions(query)
        cursor = listing.decode_cursor(query.cursor, sort=query.sort)
        cursor_condition = listing.cursor_condition(query.sort, cursor)
        if cursor_condition is not None:
            conditions.append(cursor_condition)

        total_count = (
            await self._session.scalar(
                select(func.count()).select_from(orm.Receipt).where(*listing.list_conditions(query))
            )
            or 0
        )
        records = tuple(
            await self._session.scalars(
                select(orm.Receipt)
                .where(*conditions)
                .order_by(*listing.list_order_by(query.sort))
                .limit(query.limit + 1)
            )
        )
        page_records = records[: query.limit]
        receipts = await self._records_to_read_models(page_records)
        has_next = len(records) > query.limit
        return ReceiptListPage(
            receipts=receipts,
            total_count=total_count,
            next_cursor=(
                listing.encode_cursor(sort=query.sort, record=page_records[-1])
                if has_next and page_records
                else None
            ),
            has_next=has_next,
            limit=query.limit,
        )

    async def find_by_id_for_user(
        self,
        *,
        receipt_id: UUID,
        user_id: UUID,
    ) -> ReceiptReadModel | None:
        record = await self._find_record_by_id_for_user(
            receipt_id=receipt_id,
            user_id=user_id,
        )
        if record is None:
            return None
        return await self._record_to_read_model(record)

    async def update(self, *, receipt: Receipt) -> ReceiptReadModel | None:
        record = await self._find_record_by_id_for_user(
            receipt_id=receipt.id,
            user_id=receipt.user_id,
        )
        if record is None:
            return None

        record.item_name = receipt.item_name.value
        record.brand_name = receipt.brand_name
        record.serial_number = receipt.serial_number
        record.payment_location = receipt.payment_location
        record.payment_date = receipt.payment_date.value
        record.total_amount = None if receipt.total_amount is None else receipt.total_amount.value
        record.period_months = receipt.period_months.value
        record.expires_on = receipt.expires_on
        record.category = receipt.category
        record.sub_category = receipt.sub_category
        record.memo = receipt.memo
        record.requires_physical_receipt = receipt.requires_physical_receipt

        await self._session.execute(
            delete(orm.ReceiptAttachment).where(orm.ReceiptAttachment.receipt_id == receipt.id)
        )
        for file_id in receipt.receipt_file_ids:
            self._session.add(mapper.attachment_to_record(receipt_id=receipt.id, file_id=file_id))
        await self._session.flush()
        return await self._record_to_read_model(record)

    async def delete_by_id_for_user(self, *, receipt_id: UUID, user_id: UUID) -> bool:
        record = await self._find_record_by_id_for_user(
            receipt_id=receipt_id,
            user_id=user_id,
        )
        if record is None:
            return False
        await self._session.delete(record)
        await self._session.flush()
        return True

    async def list_warranty_notification_candidates(
        self,
        *,
        query: WarrantyNotificationCandidateQuery,
    ) -> WarrantyNotificationCandidatePage:
        return await candidate_queries.list_warranty_notification_candidates(
            session=self._session,
            query=query,
        )

    async def list_receipt_registration_activity_candidates(
        self,
        *,
        query: ReceiptRegistrationActivityQuery,
    ) -> ReceiptRegistrationActivityPage:
        return await candidate_queries.list_receipt_registration_activity_candidates(
            session=self._session,
            query=query,
        )

    async def _find_record_by_id_for_user(
        self,
        *,
        receipt_id: UUID,
        user_id: UUID,
    ) -> orm.Receipt | None:
        return await self._session.scalar(
            select(orm.Receipt).where(
                orm.Receipt.id == receipt_id,
                orm.Receipt.user_id == user_id,
            )
        )

    async def _record_to_read_model(self, record: orm.Receipt) -> ReceiptReadModel:
        receipt_file_ids = await self._file_ids_for_receipt(record.id)
        return mapper.record_to_read_model(record, receipt_file_ids=receipt_file_ids)

    async def _records_to_read_models(
        self,
        records: Iterable[orm.Receipt],
    ) -> tuple[ReceiptReadModel, ...]:
        records_by_id = {record.id: record for record in records}
        receipt_file_ids = await self._file_ids_by_receipt_id(records_by_id)
        return tuple(
            mapper.record_to_read_model(
                record,
                receipt_file_ids=tuple(receipt_file_ids[record.id]),
            )
            for record in records_by_id.values()
        )

    async def _file_ids_for_receipt(self, receipt_id: UUID) -> tuple[UUID, ...]:
        result = await self._session.scalars(
            select(orm.ReceiptAttachment.file_id)
            .where(orm.ReceiptAttachment.receipt_id == receipt_id)
            .order_by(orm.ReceiptAttachment.file_id.asc())
        )
        return tuple(result)

    async def _file_ids_by_receipt_id(
        self,
        records_by_id: dict[UUID, orm.Receipt],
    ) -> dict[UUID, list[UUID]]:
        file_ids_by_receipt_id: dict[UUID, list[UUID]] = defaultdict(list)
        if not records_by_id:
            return file_ids_by_receipt_id

        result = await self._session.execute(
            select(orm.ReceiptAttachment.receipt_id, orm.ReceiptAttachment.file_id)
            .where(orm.ReceiptAttachment.receipt_id.in_(tuple(records_by_id)))
            .order_by(
                orm.ReceiptAttachment.receipt_id.asc(),
                orm.ReceiptAttachment.file_id.asc(),
            )
        )
        for receipt_id, file_id in result:
            file_ids_by_receipt_id[receipt_id].append(file_id)
        return file_ids_by_receipt_id
