from uuid import UUID

import pytest

from app.core.domain.exceptions import ValidationError
from app.modules.credits.domain import (
    CreditAmount,
    CreditBalance,
    CreditCount,
    CreditReason,
    CreditSourceType,
    FeatureKey,
    InsufficientCreditError,
    UserCredit,
)
from app.modules.credits.domain.events import CreditGranted

USER_ID = UUID("00000000-0000-0000-0000-000000000101")
SOURCE_ID = UUID("00000000-0000-0000-0000-000000000901")
EXPECTED_REASON_VALUES = {
    "monthlyOcrAllowance",
    "eventOcrAllowance",
    "ocrUsage",
}
STALE_REASON_VALUES = {
    "quizReward",
    "receiptAnalysis",
}


def test_feature_key_pins_ocr_value() -> None:
    # Given/When: credits domain이 지원하는 기능 키를 조회한다.
    ocr_feature_key = _ocr_feature_key()

    # Then: OCR ledger의 유일한 MVP feature key는 ocr이다.
    assert ocr_feature_key.value == "ocr"


def test_credit_reason_uses_ocr_ledger_values() -> None:
    # Given/When: credits domain이 공개하는 ledger reason 값을 조회한다.
    reason_values = {reason.value for reason in CreditReason}

    # Then: stale counted-feature reason은 사라지고 OCR ledger reason만 남는다.
    assert reason_values == EXPECTED_REASON_VALUES
    assert reason_values.isdisjoint(STALE_REASON_VALUES)


def test_user_credit_restore_exposes_balance_when_counts_are_consistent() -> None:
    # Given: DB에서 복원할 수 있는 일관된 크레딧 count가 있다.
    user_credit = _restore_user_credit(total_granted_count=12, used_count=5, remaining_count=7)

    # When: aggregate의 balance read model을 조회한다.
    balance = user_credit.balance

    # Then: 기존 API schema가 쓰는 CreditBalance 값으로 노출된다.
    assert balance == CreditBalance(
        total_granted_count=12,
        used_count=5,
        remaining_count=7,
    )
    assert user_credit.feature_key == _ocr_feature_key()
    assert user_credit.total_granted_count == 12
    assert user_credit.used_count == 5
    assert user_credit.remaining_count == 7


def test_credit_balance_owns_count_value_objects() -> None:
    # Given: 외부 경계에서 넘어온 raw count 값이 있다.
    balance = CreditBalance(
        total_granted_count=12,
        used_count=5,
        remaining_count=7,
    )

    # When/Then: balance 내부 상태는 CreditCount VO이고 API용 property만 int를 반환한다.
    assert balance.total_granted == CreditCount(value=12)
    assert balance.used == CreditCount(value=5)
    assert balance.remaining == CreditCount(value=7)
    assert balance.total_granted_count == 12
    assert balance.used_count == 5
    assert balance.remaining_count == 7


def test_credit_balance_accepts_count_value_objects() -> None:
    # Given: 이미 파싱된 CreditCount VO가 있다.
    total_granted = CreditCount(value=12, field_name="total_granted_count")
    used = CreditCount(value=5, field_name="used_count")
    remaining = CreditCount(value=7, field_name="remaining_count")

    # When: balance를 구성한다.
    balance = CreditBalance(
        total_granted_count=total_granted,
        used_count=used,
        remaining_count=remaining,
    )

    # Then: raw int로 되돌리지 않고 동일한 VO를 보존한다.
    assert balance.total_granted == total_granted
    assert balance.used == used
    assert balance.remaining == remaining


def test_user_credit_can_use_when_remaining_count_covers_positive_amount() -> None:
    # Given: 남은 크레딧이 7회인 사용자 크레딧 aggregate가 있다.
    user_credit = _restore_user_credit(total_granted_count=12, used_count=5, remaining_count=7)

    # When/Then: 양수 사용량만 남은 횟수 범위 안에서 허용된다.
    assert user_credit.can_use(CreditAmount(value=7)) is True
    assert user_credit.can_use(CreditAmount(value=8)) is False


def test_user_credit_use_moves_remaining_count_to_used_count() -> None:
    user_credit = _restore_user_credit(total_granted_count=12, used_count=5, remaining_count=7)

    user_credit.use(CreditAmount(value=3))

    assert user_credit.balance == CreditBalance(
        total_granted_count=12,
        used_count=8,
        remaining_count=4,
    )


def test_user_credit_use_rejects_insufficient_remaining_count() -> None:
    user_credit = _restore_user_credit(total_granted_count=12, used_count=10, remaining_count=2)

    with pytest.raises(InsufficientCreditError):
        user_credit.use(CreditAmount(value=3))

    assert user_credit.balance == CreditBalance(
        total_granted_count=12,
        used_count=10,
        remaining_count=2,
    )


def test_user_credit_grant_increases_total_and_remaining_count() -> None:
    user_credit = _restore_user_credit(total_granted_count=12, used_count=5, remaining_count=7)

    user_credit.grant(CreditAmount(value=5), reason=CreditReason.MONTHLY_OCR_ALLOWANCE)

    assert user_credit.balance == CreditBalance(
        total_granted_count=17,
        used_count=5,
        remaining_count=12,
    )


def test_user_credit_grant_records_credit_granted_event() -> None:
    user_credit = _restore_user_credit(total_granted_count=12, used_count=5, remaining_count=7)

    user_credit.grant(
        CreditAmount(value=5),
        reason=CreditReason.EVENT_OCR_ALLOWANCE,
        source_type=CreditSourceType.PROMOTION_REDEMPTION,
        source_id=SOURCE_ID,
        idempotency_key="idem-1",
    )

    events = user_credit.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, CreditGranted)
    assert event.user_id == USER_ID
    assert event.amount == 5
    assert event.reason == CreditReason.EVENT_OCR_ALLOWANCE
    assert event.source_type == CreditSourceType.PROMOTION_REDEMPTION
    assert event.source_id == SOURCE_ID
    assert event.idempotency_key == "idem-1"
    # pull_events는 큐를 비운다.
    assert user_credit.pull_events() == []


def test_user_credit_restore_does_not_record_any_event() -> None:
    user_credit = _restore_user_credit(total_granted_count=12, used_count=5, remaining_count=7)

    assert user_credit.pull_events() == []


def test_credit_amount_rejects_zero_value_with_field_message() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CreditAmount(value=0, field_name="amount")

    assert [(detail.field, detail.message) for detail in exc_info.value.details] == [
        ("amount", "크레딧 수량은 1 이상이어야 합니다.")
    ]


@pytest.mark.parametrize(
    ("total_granted_count", "used_count", "remaining_count", "field_name"),
    [
        (-1, 0, 0, "total_granted_count"),
        (1, -1, 2, "used_count"),
        (1, 2, -1, "remaining_count"),
    ],
)
def test_user_credit_restore_rejects_negative_counts(
    total_granted_count: int,
    used_count: int,
    remaining_count: int,
    field_name: str,
) -> None:
    # Given: 하나 이상의 count가 음수인 DB 복원 값이 있다.
    # When/Then: aggregate restore가 해당 필드를 ValidationError로 거절한다.
    with pytest.raises(ValidationError) as exc_info:
        _restore_user_credit(
            total_granted_count=total_granted_count,
            used_count=used_count,
            remaining_count=remaining_count,
        )

    assert field_name in [detail.field for detail in exc_info.value.details]


def test_credit_count_rejects_negative_value_with_field_message() -> None:
    # Given/When/Then: count VO가 필드명과 한글 메시지를 소유한다.
    with pytest.raises(ValidationError) as exc_info:
        CreditCount(value=-1, field_name="used_count")

    assert [(detail.field, detail.message) for detail in exc_info.value.details] == [
        ("used_count", "크레딧 횟수는 0 이상이어야 합니다.")
    ]


def test_user_credit_restore_rejects_inconsistent_total_count() -> None:
    # Given: total count가 used + remaining과 다른 DB 복원 값이 있다.
    # When/Then: aggregate restore가 합계 invariant 위반을 거절한다.
    with pytest.raises(ValidationError) as exc_info:
        _restore_user_credit(
            total_granted_count=12,
            used_count=5,
            remaining_count=6,
        )

    assert [detail.field for detail in exc_info.value.details] == ["total_granted_count"]


def _ocr_feature_key() -> FeatureKey:
    return FeatureKey.OCR


def _restore_user_credit(
    *,
    total_granted_count: int,
    used_count: int,
    remaining_count: int,
) -> UserCredit:
    return UserCredit.restore(
        user_id=USER_ID,
        feature_key=_ocr_feature_key(),
        total_granted_count=total_granted_count,
        used_count=used_count,
        remaining_count=remaining_count,
    )
