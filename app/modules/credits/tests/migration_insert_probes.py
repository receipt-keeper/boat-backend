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
    expected_constraint: str | tuple[str, ...]


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
            expected_constraint=(
                "ck_credit_transactions_reason_allowed",
                "ck_credit_transactions_reason_action_pair",
            ),
        ),
        InvalidCreditTransactionProbe(
            feature_key="ocr",
            reason="monthlyOcrAllowance",
            action="refund",
            amount=1,
            expected_constraint=(
                "ck_credit_transactions_action_allowed",
                "ck_credit_transactions_reason_action_pair",
            ),
        ),
        InvalidCreditTransactionProbe(
            feature_key="ocr",
            reason="monthlyOcrAllowance",
            action="grant",
            amount=0,
            expected_constraint="ck_credit_transactions_amount_positive",
        ),
        InvalidCreditTransactionProbe(
            feature_key="ocr",
            reason="monthlyOcrAllowance",
            action="use",
            amount=1,
            expected_constraint="ck_credit_transactions_reason_action_pair",
        ),
        InvalidCreditTransactionProbe(
            feature_key="ocr",
            reason="ocrUsage",
            action="grant",
            amount=1,
            expected_constraint="ck_credit_transactions_reason_action_pair",
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
                        id,
                        user_id,
                        feature_key,
                        reason,
                        action,
                        amount
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
        failed_constraint = str(exc_info.value.orig)
        if isinstance(probe.expected_constraint, str):
            assert probe.expected_constraint in failed_constraint
        else:
            assert any(
                expected_constraint in failed_constraint
                for expected_constraint in probe.expected_constraint
            )
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
