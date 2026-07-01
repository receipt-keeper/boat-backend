from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class InvalidCreditTransactionProbe:
    feature_key: str
    reason: str
    action: str
    amount: int
    expected_constraint: str


@dataclass(frozen=True, slots=True)
class InvalidUserCreditProbe:
    user_id: str
    feature_key: str
    total_granted_count: int
    used_count: int
    remaining_count: int
    expected_constraint: str


@dataclass(frozen=True, slots=True)
class ValidCreditTransactionProbe:
    transaction_id: str
    reason: str
    action: str


async def assert_credit_transaction_insert_probes(connection: AsyncConnection) -> None:
    for probe in (
        InvalidCreditTransactionProbe(
            feature_key="receipt_analysis",
            reason="monthlyOcrAllowance",
            action="grant",
            amount=1,
            expected_constraint="ck_credit_transactions_feature_key_allowed",
        ),
        InvalidCreditTransactionProbe(
            feature_key="ocr",
            reason="quizReward",
            action="grant",
            amount=1,
            expected_constraint="ck_credit_transactions_reason_allowed",
        ),
        InvalidCreditTransactionProbe(
            feature_key="ocr",
            reason="monthlyOcrAllowance",
            action="refund",
            amount=1,
            expected_constraint="ck_credit_transactions_action_allowed",
        ),
        InvalidCreditTransactionProbe(
            feature_key="ocr",
            reason="monthlyOcrAllowance",
            action="grant",
            amount=0,
            expected_constraint="ck_credit_transactions_amount_positive",
        ),
    ):
        await _assert_invalid_credit_transaction_is_rejected(connection, probe)

    for probe in (
        ValidCreditTransactionProbe(
            transaction_id="00000000-0000-0000-0000-000000000401",
            reason="monthlyOcrAllowance",
            action="grant",
        ),
        ValidCreditTransactionProbe(
            transaction_id="00000000-0000-0000-0000-000000000402",
            reason="eventOcrAllowance",
            action="grant",
        ),
        ValidCreditTransactionProbe(
            transaction_id="00000000-0000-0000-0000-000000000403",
            reason="ocrUsage",
            action="use",
        ),
    ):
        await _assert_valid_credit_transaction_is_accepted(connection, probe)


async def assert_user_credit_insert_probes(connection: AsyncConnection) -> None:
    for probe in (
        InvalidUserCreditProbe(
            user_id="00000000-0000-0000-0000-000000000301",
            feature_key="receipt_analysis",
            total_granted_count=1,
            used_count=0,
            remaining_count=1,
            expected_constraint="ck_user_credits_feature_key_allowed",
        ),
        InvalidUserCreditProbe(
            user_id="00000000-0000-0000-0000-000000000302",
            feature_key="ocr",
            total_granted_count=0,
            used_count=-1,
            remaining_count=1,
            expected_constraint="ck_user_credits_used_count_non_negative",
        ),
        InvalidUserCreditProbe(
            user_id="00000000-0000-0000-0000-000000000303",
            feature_key="ocr",
            total_granted_count=0,
            used_count=1,
            remaining_count=-1,
            expected_constraint="ck_user_credits_remaining_count_non_negative",
        ),
        InvalidUserCreditProbe(
            user_id="00000000-0000-0000-0000-000000000304",
            feature_key="ocr",
            total_granted_count=3,
            used_count=1,
            remaining_count=1,
            expected_constraint="ck_user_credits_counts_consistent",
        ),
    ):
        await _assert_invalid_user_credit_is_rejected(connection, probe)
    await _assert_valid_user_credit_is_accepted(connection)


async def _assert_invalid_credit_transaction_is_rejected(
    connection: AsyncConnection,
    probe: InvalidCreditTransactionProbe,
) -> None:
    try:
        with pytest.raises(DBAPIError) as exc_info:
            await connection.execute(
                text(
                    """
                    INSERT INTO credit_transactions (
                        id, user_id, feature_key, reason, action, amount
                    )
                    VALUES (
                        '00000000-0000-0000-0000-000000000201',
                        '00000000-0000-0000-0000-000000000202',
                        :feature_key,
                        :reason,
                        :action,
                        :amount
                    )
                    """
                ),
                {
                    "feature_key": probe.feature_key,
                    "reason": probe.reason,
                    "action": probe.action,
                    "amount": probe.amount,
                },
            )
        assert probe.expected_constraint in str(exc_info.value.orig)
    finally:
        await connection.rollback()


async def _assert_invalid_user_credit_is_rejected(
    connection: AsyncConnection,
    probe: InvalidUserCreditProbe,
) -> None:
    try:
        with pytest.raises(DBAPIError) as exc_info:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_credits (
                        user_id,
                        feature_key,
                        total_granted_count,
                        used_count,
                        remaining_count
                    )
                    VALUES (
                        :user_id,
                        :feature_key,
                        :total_granted_count,
                        :used_count,
                        :remaining_count
                    )
                    """
                ),
                {
                    "user_id": probe.user_id,
                    "feature_key": probe.feature_key,
                    "total_granted_count": probe.total_granted_count,
                    "used_count": probe.used_count,
                    "remaining_count": probe.remaining_count,
                },
            )
        assert probe.expected_constraint in str(exc_info.value.orig)
    finally:
        await connection.rollback()


async def _assert_valid_credit_transaction_is_accepted(
    connection: AsyncConnection,
    probe: ValidCreditTransactionProbe,
) -> None:
    try:
        await connection.execute(
            text(
                """
                INSERT INTO credit_transactions (
                    id, user_id, feature_key, reason, action, amount
                )
                VALUES (
                    :transaction_id,
                    '00000000-0000-0000-0000-000000000202',
                    'ocr',
                    :reason,
                    :action,
                    1
                )
                """
            ),
            {
                "transaction_id": probe.transaction_id,
                "reason": probe.reason,
                "action": probe.action,
            },
        )
    finally:
        await connection.rollback()


async def _assert_valid_user_credit_is_accepted(connection: AsyncConnection) -> None:
    try:
        await connection.execute(
            text(
                """
                INSERT INTO user_credits (
                    user_id,
                    feature_key,
                    total_granted_count,
                    used_count,
                    remaining_count
                )
                VALUES (
                    '00000000-0000-0000-0000-000000000501',
                    'ocr',
                    3,
                    1,
                    2
                )
                """
            )
        )
    finally:
        await connection.rollback()
