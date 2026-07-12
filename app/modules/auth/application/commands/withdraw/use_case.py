from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.application.ports.benefit_subject_handle import (
    BenefitSubjectHandleProvider,
)
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.credit_lifecycle import CreditWithdrawalCleaner
from app.modules.auth.application.ports.push_token_lifecycle import PushTokenWithdrawalCleaner
from app.modules.auth.domain.events import AccountWithdrawn
from app.modules.users.application.commands.withdrawal_cleanup.command import (
    WithdrawalCleanupCommand,
)
from app.modules.users.application.commands.withdrawal_cleanup.use_case import (
    WithdrawalCleanupCommandUseCase,
)


class WithdrawAccountCommandUseCase:
    def __init__(
        self,
        *,
        credential_repository: CredentialRepository,
        withdrawal_cleanup_command_use_case: WithdrawalCleanupCommandUseCase,
        credit_withdrawal_cleaner: CreditWithdrawalCleaner,
        push_token_withdrawal_cleaner: PushTokenWithdrawalCleaner,
        benefit_subject_handle_provider: BenefitSubjectHandleProvider,
        unit_of_work: UnitOfWork,
        event_publisher: EventPublisher,
    ) -> None:
        self._credential_repository = credential_repository
        self._withdrawal_cleanup_command_use_case = withdrawal_cleanup_command_use_case
        self._credit_withdrawal_cleaner = credit_withdrawal_cleaner
        self._push_token_withdrawal_cleaner = push_token_withdrawal_cleaner
        self._benefit_subject_handle_provider = benefit_subject_handle_provider
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher

    async def execute(self, command: WithdrawAccountCommand) -> None:
        # 삭제 직전에 연결된 external identity의 uid로 candidate handle을 계산해
        # credits가 가입 보너스 claim을 보존 상태로 전환(purge_after 설정)할 수 있게
        # 한다. 연결된 identity가 하나도 없으면(엣지) 빈 목록을 전달해 credits가
        # 전량 삭제로 폴백하게 한다. 소셜 링크된 identity는 모두 같은 Firebase uid를
        # 공유하므로 첫 row의 subject만으로 충분하다.
        identities = await self._credential_repository.list_external_identities(
            credentials_id=command.credentials_id,
        )
        candidate_handles = (
            self._benefit_subject_handle_provider.candidate_handles(
                subject=identities[0].subject.value,
            )
            if identities
            else ()
        )

        # 삭제 경로는 애그리거트를 로드하지 않고 user_id/credentials_id만으로 진행되므로
        # (성능/락 최소화), AccountWithdrawn은 엔티티 팩토리가 아니라 이 use case에서
        # 직접 기록한다 (users의 UserWithdrawn과 동일한 근거).
        await self._credential_repository.delete_account_auth_state(
            user_id=command.user_id,
            credentials_id=command.credentials_id,
        )
        await self._event_publisher.publish(
            [
                AccountWithdrawn(
                    credentials_id=command.credentials_id,
                    user_id=command.user_id,
                )
            ]
        )
        await self._withdrawal_cleanup_command_use_case.execute(
            WithdrawalCleanupCommand(user_id=command.user_id)
        )
        await self._credit_withdrawal_cleaner.delete_account_state(
            user_id=command.user_id,
            candidate_handles=candidate_handles,
        )
        await self._push_token_withdrawal_cleaner.delete_account_state(user_id=command.user_id)
        await self._unit_of_work.commit()
