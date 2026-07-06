from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.modules.credits.application.commands.use_credit.command import UseCreditCommand
from app.modules.credits.application.ports.credit_repository import (
    CreditRepository,
    CreditTransactionAppend,
)
from app.modules.credits.domain import CreditAction
from app.modules.credits.domain.events import CreditUsed


class FinalizeCreditUsageCommandUseCase:
    """예약(reserve)된 크레딧 사용을 확정(commit)한다.

    `ReserveCreditCommandUseCase`가 이미 aggregate(`UserCredit.use()`)를 통해
    잔액을 차감했으나 그 인스턴스는 이 use case로 전달되지 않는다(reserve/finalize가
    서로 다른 호출로 분리되어 있고, reserve는 커밋하지 않는 1단계이기 때문). 따라서
    `CreditUsed`는 aggregate의 `record_event`가 아니라 이 use case에서 커맨드로부터
    직접 구성한다 - finalize가 실제 사용 확정의 유일한 커밋 지점이므로 정확히 1회
    발행이 보장된다.
    """

    def __init__(
        self,
        *,
        credit_repository: CreditRepository,
        unit_of_work: UnitOfWork,
        event_publisher: EventPublisher,
    ) -> None:
        self._credit_repository = credit_repository
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher

    async def execute(self, command: UseCreditCommand) -> None:
        await self._credit_repository.append_transaction(
            transaction=CreditTransactionAppend(
                user_id=command.user_id,
                reason=command.reason,
                action=CreditAction.USE,
                amount=command.amount,
            )
        )
        await self._event_publisher.publish(
            [
                CreditUsed(
                    user_id=command.user_id,
                    amount=command.amount.value,
                    reason=command.reason,
                )
            ]
        )
        await self._unit_of_work.commit()
