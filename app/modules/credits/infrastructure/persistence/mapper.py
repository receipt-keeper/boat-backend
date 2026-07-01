from uuid import UUID

from app.modules.credits.application.ports.credit_repository import CreditTransactionListItem
from app.modules.credits.domain import (
    CreditAction,
    CreditBalance,
    CreditReason,
    FeatureKey,
    UserCredit,
)
from app.modules.credits.infrastructure.persistence import orm


def user_credit_to_balance(record: orm.UserCredit | None, *, user_id: UUID) -> CreditBalance:
    if record is None:
        return UserCredit.restore(
            user_id=user_id,
            feature_key=FeatureKey.OCR,
            total_granted_count=0,
            used_count=0,
            remaining_count=0,
        ).balance
    return UserCredit.restore(
        user_id=record.user_id,
        feature_key=FeatureKey(record.feature_key),
        total_granted_count=record.total_granted_count,
        used_count=record.used_count,
        remaining_count=record.remaining_count,
    ).balance


def transaction_to_list_item(record: orm.CreditTransaction) -> CreditTransactionListItem:
    return CreditTransactionListItem(
        transaction_id=record.id,
        user_id=record.user_id,
        reason=CreditReason(record.reason),
        action=CreditAction(record.action),
        amount=record.amount,
        created_at=record.created_at,
    )
