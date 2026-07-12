from collections.abc import AsyncIterator

from app.modules.notifications.application.commands.create_due_notifications.command import (
    CreateDueNotificationsCommand,
)
from app.modules.notifications.application.due_notification import (
    DueNotification,
    warranty_expiry_notification,
)
from app.modules.notifications.domain.due_notification import (
    DueNotificationRule,
    observation_cutoff_for,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.query import (
    ListReceiptsExpiringOnQuery,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.use_case import (
    ListReceiptsExpiringOnQueryUseCase,
)
from app.modules.users.application.queries.get_existing_user_ids.query import (
    GetExistingUserIdsQuery,
)
from app.modules.users.application.queries.get_existing_user_ids.use_case import (
    GetExistingUserIdsQueryUseCase,
)


class WarrantyExpiryNotifications:
    def __init__(
        self,
        *,
        list_receipts_expiring_on: ListReceiptsExpiringOnQueryUseCase,
        get_existing_user_ids: GetExistingUserIdsQueryUseCase,
    ) -> None:
        self._list_receipts_expiring_on = list_receipts_expiring_on
        self._get_existing_user_ids = get_existing_user_ids

    async def iter_due_notifications(
        self,
        *,
        due_rule: DueNotificationRule,
        command: CreateDueNotificationsCommand,
    ) -> AsyncIterator[DueNotification]:
        offset_days = due_rule.rule.day_offset
        if offset_days is None:
            return

        observed_before = observation_cutoff_for(due_rule)
        cursor = None
        while True:
            page = await self._list_receipts_expiring_on.execute(
                ListReceiptsExpiringOnQuery(
                    target_date=due_rule.target_date,
                    offset_days=offset_days,
                    observed_before=observed_before,
                    limit=command.batch_size,
                    cursor_receipt_id=cursor,
                )
            )
            existing_user_ids = (
                await self._get_existing_user_ids.execute(
                    GetExistingUserIdsQuery(
                        user_ids=tuple(receipt.user_id for receipt in page.receipts)
                    )
                )
            ).user_ids
            for receipt in page.receipts:
                if receipt.user_id not in existing_user_ids:
                    continue
                yield warranty_expiry_notification(
                    due_rule=due_rule,
                    user_id=receipt.user_id,
                    receipt_id=receipt.receipt_id,
                    item_name=receipt.item_name,
                    sub_category=receipt.sub_category,
                )
            if not page.has_next:
                return
            if page.next_cursor_receipt_id is None:
                raise RuntimeError("만료 예정 영수증 조회 cursor가 누락되었습니다.")
            cursor = page.next_cursor_receipt_id
