from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.modules.promotions.application.commands.create_promotion_redemption.result import (
    CreatePromotionRedemptionResult,
)
from app.modules.promotions.application.ports.credit_grant import (
    PromotionCreditGrant,
    PromotionCreditGrantPort,
)
from app.modules.promotions.application.ports.promotion_repository import (
    PromotionRepository,
)
from app.modules.promotions.application.redemption_window import (
    current_user_redemption_window,
)
from app.modules.promotions.domain.exceptions import (
    PromotionNotFoundError,
    PromotionRedemptionConflictError,
)
from app.modules.promotions.domain.model import (
    Promotion,
    PromotionCode,
    PromotionContent,
    PromotionKind,
    PromotionRedemption,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class PromotionRedemptionReplay:
    user_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class PromotionRedemptionAttempt:
    user_id: UUID
    promotion: Promotion
    promotion_code: PromotionCode | None
    idempotency_key: str


class PromotionRedemptionExecutor:
    def __init__(
        self,
        *,
        promotion_repository: PromotionRepository,
        credit_grant_port: PromotionCreditGrantPort,
        unit_of_work: UnitOfWork,
        event_publisher: EventPublisher,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._promotion_repository = promotion_repository
        self._credit_grant_port = credit_grant_port
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher
        self._clock = clock

    async def replay_if_existing(
        self,
        replay: PromotionRedemptionReplay,
    ) -> CreatePromotionRedemptionResult | None:
        existing = await self._promotion_repository.find_redemption_by_idempotency_key(
            idempotency_key=replay.idempotency_key
        )
        if existing is None:
            return None

        promotion = await self._promotion_repository.find_promotion_for_update(
            promotion_id=existing.promotion_id,
        )
        if promotion is None:
            raise PromotionNotFoundError()
        now = self._clock()
        user_redemption_count = await self._user_redemption_count(
            user_id=replay.user_id,
            promotion=promotion,
            at=now,
        )
        balance = await self._credit_grant_port.get_ocr_credit_balance(
            user_id=replay.user_id,
        )
        content = await self._promotion_repository.find_content_by_promotion_id(
            promotion_id=promotion.id,
        )
        return _result(
            redemption=existing,
            promotion=promotion,
            banner_image_url=_banner_image_url(content),
            already_redeemed=True,
            credit_granted=False,
            user_redemption_count=user_redemption_count,
            credit_balance_after=balance.total_granted_count,
            credit_remaining_after=balance.remaining_count,
        )

    async def redeem(
        self,
        attempt: PromotionRedemptionAttempt,
    ) -> CreatePromotionRedemptionResult:
        now = self._clock()
        if attempt.promotion_code is not None:
            attempt.promotion_code.ensure_redeemable(at=now)
        attempt.promotion.ensure_redeemable(at=now)
        if attempt.promotion.kind == PromotionKind.REWARDED_AD:
            balance = await self._credit_grant_port.get_ocr_credit_balance(
                user_id=attempt.user_id,
            )
            if balance.remaining_count != 0:
                raise PromotionRedemptionConflictError(
                    "남은 OCR 분석 횟수를 모두 사용한 후 광고 보상을 받을 수 있습니다."
                )
        user_redemption_count = await self._user_redemption_count(
            user_id=attempt.user_id,
            promotion=attempt.promotion,
            at=now,
        )
        attempt.promotion.ensure_user_can_redeem(user_redemption_count=user_redemption_count)

        redemption = PromotionRedemption.create_granted(
            promotion_id=attempt.promotion.id,
            promotion_code_id=_promotion_code_id(attempt.promotion_code),
            user_id=attempt.user_id,
            idempotency_key=attempt.idempotency_key,
            redeemed_at=now,
            benefit_amount=attempt.promotion.benefit_amount.value,
        )
        attempt.promotion.record_redemption()
        if attempt.promotion_code is not None:
            attempt.promotion_code.record_redemption()
        await self._promotion_repository.create_redemption(redemption=redemption)
        await self._promotion_repository.save_promotion(promotion=attempt.promotion)
        if attempt.promotion_code is not None:
            await self._promotion_repository.save_code(code=attempt.promotion_code)
        # 발행은 credits 동기 호출·UoW commit 이전에 수행한다 - 같은 세션에 insert된
        # outbox row가 아래 credit grant/commit 실패 시의 rollback과 함께 원자적으로
        # 소거되도록 하기 위함이다(멱등 replay에서 유령 이벤트 방지, credits T3와 동일 원칙).
        events = redemption.pull_events()
        await self._event_publisher.publish(events)
        grant_result = await self._credit_grant_port.grant_ocr_credit(
            grant=_credit_grant(
                redemption=redemption,
                amount=attempt.promotion.benefit_amount.value,
                idempotency_key=attempt.idempotency_key,
            )
        )
        await self._unit_of_work.commit()
        content = await self._promotion_repository.find_content_by_promotion_id(
            promotion_id=attempt.promotion.id,
        )
        return _result(
            redemption=redemption,
            promotion=attempt.promotion,
            banner_image_url=_banner_image_url(content),
            already_redeemed=False,
            credit_granted=True,
            user_redemption_count=user_redemption_count + 1,
            credit_balance_after=grant_result.credit_balance_after,
            credit_remaining_after=grant_result.credit_remaining_after,
        )

    async def _user_redemption_count(
        self,
        *,
        user_id: UUID,
        promotion: Promotion,
        at: datetime,
    ) -> int:
        window = current_user_redemption_window(promotion=promotion, at=at)
        return await self._promotion_repository.count_user_redemptions(
            user_id=user_id,
            promotion_id=promotion.id,
            redeemed_at_from=window.starts_at,
            redeemed_at_before=window.expires_at,
        )


def _credit_grant(
    *,
    redemption: PromotionRedemption,
    amount: int,
    idempotency_key: str,
) -> PromotionCreditGrant:
    return PromotionCreditGrant(
        user_id=redemption.user_id,
        amount=amount,
        redemption_id=redemption.id,
        idempotency_key=idempotency_key,
    )


def _promotion_code_id(promotion_code: PromotionCode | None) -> UUID | None:
    if promotion_code is None:
        return None
    return promotion_code.id


def _result(
    *,
    redemption: PromotionRedemption,
    promotion: Promotion,
    banner_image_url: str | None,
    already_redeemed: bool,
    credit_granted: bool,
    user_redemption_count: int,
    credit_balance_after: int | None,
    credit_remaining_after: int | None,
) -> CreatePromotionRedemptionResult:
    return CreatePromotionRedemptionResult(
        redemption_id=redemption.id,
        promotion_id=redemption.promotion_id,
        promotion_code_id=redemption.promotion_code_id,
        status=redemption.status,
        already_redeemed=already_redeemed,
        credit_granted=credit_granted,
        kind=promotion.kind,
        benefit_amount=promotion.benefit_amount.value,
        remaining_redemptions=_remaining_redemptions(promotion),
        max_redemptions_per_user=promotion.max_redemptions_per_user,
        remaining_redemptions_for_user=max(
            promotion.max_redemptions_per_user - user_redemption_count,
            0,
        ),
        credit_balance_after=credit_balance_after,
        credit_remaining_after=credit_remaining_after,
        banner_image_url=banner_image_url,
    )


def _remaining_redemptions(promotion: Promotion) -> int | None:
    if promotion.max_redemptions is None:
        return None
    return max(promotion.max_redemptions - promotion.times_redeemed, 0)


def _banner_image_url(content: PromotionContent | None) -> str | None:
    if content is None:
        return None
    return content.banner_image_url
