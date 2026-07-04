from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class InvalidUserCreditProbe:
    user_id: str
    feature_key: str
    total_granted_count: int
    used_count: int
    remaining_count: int
    expected_constraint: str


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
