from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.promotions.domain.model import PromotionContext
from app.modules.promotions.infrastructure.persistence import mapper, orm
from app.modules.promotions.infrastructure.persistence.repository import (
    SqlAlchemyPromotionRepository,
)


def test_promotion_mapper_round_trips_signup_context() -> None:
    # Given: DB에서 읽은 signup context promotion row가 있다.
    record = orm.Promotion(
        id=UUID("00000000-0000-0000-0000-000000000903"),
        name="신규 가입 OCR 크레딧",
        active=True,
        starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        expires_at=None,
        max_redemptions=None,
        times_redeemed=0,
        max_redemptions_per_user=1,
        benefit_feature_key="ocr",
        context="signup",
        benefit_amount=5,
    )

    # When: persistence mapper로 domain entity를 복원한다.
    promotion = mapper.promotion_to_domain(record)

    # Then: signup context가 domain enum으로 보존된다.
    assert promotion.context == PromotionContext.SIGNUP


def test_redemption_mapper_round_trips_beneficiary_key() -> None:
    # Given: 영속 수혜자 키를 가진 redemption row가 있다.
    record = orm.PromotionRedemption(
        id=UUID("00000000-0000-0000-0000-000000000904"),
        promotion_id=UUID("00000000-0000-0000-0000-000000000905"),
        promotion_code_id=None,
        user_id=UUID("00000000-0000-0000-0000-000000000906"),
        beneficiary_key="signup:stable-subject",
        status="granted",
        idempotency_key="signup-redemption",
        failure_reason=None,
        redeemed_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    # When: persistence mapper로 domain entity를 왕복한다.
    redemption = mapper.redemption_to_domain(record)
    restored_record = mapper.redemption_to_record(redemption)

    # Then: beneficiary key가 손실 없이 유지된다.
    assert redemption.beneficiary_key == "signup:stable-subject"
    assert restored_record.beneficiary_key == "signup:stable-subject"


async def test_command_repository_finds_signup_promotion_and_beneficiary_redemption(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: signup promotion과 영속 수혜자 key를 가진 redemption이 저장돼 있다.
    promotion_id = UUID("00000000-0000-0000-0000-000000000907")
    beneficiary_key = "signup:stable-subject"
    async with postgres_session_factory() as session:
        session.add(
            orm.Promotion(
                id=promotion_id,
                name="신규 가입 OCR 크레딧",
                active=True,
                starts_at=datetime(2026, 7, 1, tzinfo=UTC),
                expires_at=None,
                max_redemptions=None,
                times_redeemed=0,
                max_redemptions_per_user=1,
                benefit_feature_key="ocr",
                context="signup",
                benefit_amount=5,
            )
        )
        session.add(
            orm.PromotionRedemption(
                id=UUID("00000000-0000-0000-0000-000000000908"),
                promotion_id=promotion_id,
                promotion_code_id=None,
                user_id=UUID("00000000-0000-0000-0000-000000000909"),
                beneficiary_key=beneficiary_key,
                status="granted",
                idempotency_key="signup-redemption-repository",
                failure_reason=None,
                redeemed_at=datetime(2026, 7, 1, tzinfo=UTC),
            )
        )
        await session.commit()
        repository = SqlAlchemyPromotionRepository(session)

        # When: command-only lock lookup과 beneficiary lookup을 호출한다.
        promotion = await repository.find_current_ocr_credit_promotion_for_update(
            at=datetime(2026, 7, 2, tzinfo=UTC),
            context=PromotionContext.SIGNUP,
        )
        redemption = await repository.find_redemption_by_promotion_and_beneficiary(
            promotion_id=promotion_id,
            beneficiary_key=beneficiary_key,
        )

    # Then: signup promotion과 대상 redemption이 각각 복원된다.
    assert promotion is not None
    assert promotion.id == promotion_id
    assert redemption is not None
    assert redemption.beneficiary_key == beneficiary_key
