from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class InvalidPromotionProbe:
    benefit_feature_key: str
    benefit_amount: int
    expected_constraint: str


@dataclass(frozen=True, slots=True)
class DuplicateProbe:
    name: str
    statement: str
    expected_constraint: str


async def assert_invalid_promotion_insert_probes(
    connection: AsyncConnection,
) -> list[str]:
    observed_failures: list[str] = []
    for probe in (
        InvalidPromotionProbe(
            benefit_feature_key="receipt_analysis",
            benefit_amount=10,
            expected_constraint="ck_promotions_benefit_feature_key_allowed",
        ),
        InvalidPromotionProbe(
            benefit_feature_key="ocr",
            benefit_amount=-1,
            expected_constraint="ck_promotions_benefit_amount_positive",
        ),
    ):
        observed_failures.append(await _assert_invalid_promotion_is_rejected(connection, probe))

    for probe in (
        DuplicateProbe(
            name="duplicate promotion_codes.code",
            statement="""
                INSERT INTO promotion_codes (
                    id,
                    promotion_id,
                    code,
                    active
                )
                VALUES (
                    '00000000-0000-0000-0000-000000000203',
                    '00000000-0000-0000-0000-000000000101',
                    'WELCOME2026',
                    true
                )
            """,
            expected_constraint="ix_promotion_codes_code_unique",
        ),
        DuplicateProbe(
            name="case-variant duplicate promotion_codes.code",
            statement="""
                INSERT INTO promotion_codes (
                    id,
                    promotion_id,
                    code,
                    active
                )
                VALUES (
                    '00000000-0000-0000-0000-000000000204',
                    '00000000-0000-0000-0000-000000000101',
                    'welcome2026',
                    true
                )
            """,
            expected_constraint="ix_promotion_codes_code_unique",
        ),
        DuplicateProbe(
            name="duplicate promotion_redemptions.idempotency_key",
            statement="""
                INSERT INTO promotion_redemptions (
                    id,
                    promotion_id,
                    promotion_code_id,
                    user_id,
                    status,
                    idempotency_key
                )
                VALUES (
                    '00000000-0000-0000-0000-000000000303',
                    '00000000-0000-0000-0000-000000000101',
                    '00000000-0000-0000-0000-000000000201',
                    '00000000-0000-0000-0000-000000000302',
                    'granted',
                    'promotionRedemption:demo'
                )
            """,
            expected_constraint="uq_promotion_redemptions_idempotency_key",
        ),
        DuplicateProbe(
            name="duplicate promotion_redemptions.user_id/promotion_id",
            statement="""
                INSERT INTO promotion_redemptions (
                    id,
                    promotion_id,
                    user_id,
                    status,
                    idempotency_key
                )
                VALUES (
                    '00000000-0000-0000-0000-000000000304',
                    '00000000-0000-0000-0000-000000000101',
                    '00000000-0000-0000-0000-000000000301',
                    'granted',
                    'promotionRedemption:other-key'
                )
            """,
            expected_constraint="uq_promotion_redemptions_user_id_promotion_id",
        ),
    ):
        await _insert_valid_promotion(connection)
        await _insert_valid_promotion_code(connection)
        await _insert_valid_redemption(connection)
        observed_failures.append(await _assert_duplicate_probe_is_rejected(connection, probe))

    await connection.rollback()
    return observed_failures


async def _assert_invalid_promotion_is_rejected(
    connection: AsyncConnection,
    probe: InvalidPromotionProbe,
) -> str:
    try:
        with pytest.raises(DBAPIError) as exc_info:
            await connection.execute(
                text(
                    """
                    INSERT INTO promotions (
                        id,
                        name,
                        active,
                        starts_at,
                        benefit_feature_key,
                        benefit_amount
                    )
                    VALUES (
                        '00000000-0000-0000-0000-000000000001',
                        'invalid promotion',
                        true,
                        now(),
                        :benefit_feature_key,
                        :benefit_amount
                    )
                    """
                ),
                {
                    "benefit_feature_key": probe.benefit_feature_key,
                    "benefit_amount": probe.benefit_amount,
                },
            )
        failure = str(exc_info.value.orig)
        assert probe.expected_constraint in failure
        return f"{probe.expected_constraint}: {failure}"
    finally:
        await connection.rollback()


async def _assert_duplicate_probe_is_rejected(
    connection: AsyncConnection,
    probe: DuplicateProbe,
) -> str:
    try:
        with pytest.raises(DBAPIError) as exc_info:
            await connection.execute(text(probe.statement))
        failure = str(exc_info.value.orig)
        assert probe.expected_constraint in failure
        return f"{probe.name}: {failure}"
    finally:
        await connection.rollback()


async def _insert_valid_promotion(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO promotions (
                id,
                name,
                active,
                starts_at,
                benefit_feature_key,
                benefit_amount
            )
            VALUES (
                '00000000-0000-0000-0000-000000000101',
                'valid promotion',
                true,
                now(),
                'ocr',
                10
            )
            """
        )
    )


async def _insert_valid_promotion_code(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO promotion_codes (
                id,
                promotion_id,
                code,
                active
            )
            VALUES (
                '00000000-0000-0000-0000-000000000201',
                '00000000-0000-0000-0000-000000000101',
                'WELCOME2026',
                true
            )
            """
        )
    )


async def _insert_valid_redemption(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO promotion_redemptions (
                id,
                promotion_id,
                promotion_code_id,
                user_id,
                status,
                idempotency_key
            )
            VALUES (
                '00000000-0000-0000-0000-000000000301',
                '00000000-0000-0000-0000-000000000101',
                '00000000-0000-0000-0000-000000000201',
                '00000000-0000-0000-0000-000000000301',
                'granted',
                'promotionRedemption:demo'
            )
            """
        )
    )
