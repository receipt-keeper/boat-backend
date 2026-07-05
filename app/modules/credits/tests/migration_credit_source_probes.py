import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection


async def assert_credit_source_insert_probes(connection: AsyncConnection) -> None:
    await _assert_invalid_source_type_is_rejected(connection)
    await _assert_partial_source_type_is_rejected(connection)
    await _assert_partial_source_id_is_rejected(connection)
    await _assert_duplicate_idempotency_key_is_rejected(connection)
    await _assert_duplicate_source_tuple_is_rejected(connection)


async def _assert_invalid_source_type_is_rejected(connection: AsyncConnection) -> None:
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
                        amount,
                        source_type,
                        source_id
                    )
                    VALUES (
                        '00000000-0000-0000-0000-000000000601',
                        '00000000-0000-0000-0000-000000000202',
                        'ocr',
                        'eventOcrAllowance',
                        'grant',
                        1,
                        'manualAdjustment',
                        '00000000-0000-0000-0000-000000000602'
                    )
                    """
                )
            )
        assert "ck_credit_transactions_source_type_allowed" in str(exc_info.value.orig)
    finally:
        await connection.rollback()


async def _assert_duplicate_idempotency_key_is_rejected(connection: AsyncConnection) -> None:
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
                        amount,
                        idempotency_key
                    )
                    VALUES
                        (
                            '00000000-0000-0000-0000-000000000611',
                            '00000000-0000-0000-0000-000000000202',
                            'ocr',
                            'eventOcrAllowance',
                            'grant',
                            1,
                            'promotionRedemption:duplicate'
                        ),
                        (
                            '00000000-0000-0000-0000-000000000612',
                            '00000000-0000-0000-0000-000000000203',
                            'ocr',
                            'eventOcrAllowance',
                            'grant',
                            1,
                            'promotionRedemption:duplicate'
                        )
                    """
                )
            )
        assert "ix_credit_transactions_idempotency_key_unique" in str(exc_info.value.orig)
    finally:
        await connection.rollback()


async def _assert_partial_source_type_is_rejected(connection: AsyncConnection) -> None:
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
                        amount,
                        source_type
                    )
                    VALUES (
                        '00000000-0000-0000-0000-000000000621',
                        '00000000-0000-0000-0000-000000000202',
                        'ocr',
                        'eventOcrAllowance',
                        'grant',
                        1,
                        'promotionRedemption'
                    )
                    """
                )
            )
        assert "ck_credit_transactions_source_pair_complete" in str(exc_info.value.orig)
    finally:
        await connection.rollback()


async def _assert_partial_source_id_is_rejected(connection: AsyncConnection) -> None:
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
                        amount,
                        source_id
                    )
                    VALUES (
                        '00000000-0000-0000-0000-000000000622',
                        '00000000-0000-0000-0000-000000000202',
                        'ocr',
                        'eventOcrAllowance',
                        'grant',
                        1,
                        '00000000-0000-0000-0000-000000000623'
                    )
                    """
                )
            )
        assert "ck_credit_transactions_source_pair_complete" in str(exc_info.value.orig)
    finally:
        await connection.rollback()


async def _assert_duplicate_source_tuple_is_rejected(connection: AsyncConnection) -> None:
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
                        amount,
                        source_type,
                        source_id
                    )
                    VALUES
                        (
                            '00000000-0000-0000-0000-000000000701',
                            '00000000-0000-0000-0000-000000000202',
                            'ocr',
                            'eventOcrAllowance',
                            'grant',
                            1,
                            'promotionRedemption',
                            '00000000-0000-0000-0000-000000000702'
                        ),
                        (
                            '00000000-0000-0000-0000-000000000703',
                            '00000000-0000-0000-0000-000000000202',
                            'ocr',
                            'eventOcrAllowance',
                            'grant',
                            1,
                            'promotionRedemption',
                            '00000000-0000-0000-0000-000000000702'
                        )
                    """
                )
            )
        assert "ix_credit_transactions_source_unique" in str(exc_info.value.orig)
    finally:
        await connection.rollback()
