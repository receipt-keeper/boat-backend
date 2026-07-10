import ast
from collections.abc import Callable
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest

from app.core.domain.exceptions import ValidationError
from app.modules.receipts.application.ports.receipt_repository import (
    ReceiptRegistrationActivityQuery,
    WarrantyNotificationCandidateQuery,
)

_RECEIPT_REPOSITORY = Path(__file__).parents[1] / "application" / "ports" / "receipt_repository.py"
_SCHEDULER_CANDIDATE_QUERY_NAMES = {
    "WarrantyNotificationCandidateQuery",
    "ReceiptRegistrationActivityQuery",
}
_TARGET_DATE = date(2026, 7, 9)
_USER_ID = UUID("00000000-0000-0000-0000-000000000101")
type _MalformedQueryFactory = Callable[
    [],
    WarrantyNotificationCandidateQuery | ReceiptRegistrationActivityQuery,
]


@pytest.mark.parametrize(
    ("make_query", "expected_details"),
    [
        (
            lambda: WarrantyNotificationCandidateQuery(
                target_date=_TARGET_DATE,
                offset_days=-1,
                limit=10,
            ),
            [("offsetDays", "보증 알림 후보 조회 offsetDays가 올바르지 않습니다.")],
        ),
        (
            lambda: WarrantyNotificationCandidateQuery(
                target_date=_TARGET_DATE,
                offset_days=30,
                limit=0,
            ),
            [("batchSize", "보증 알림 후보 조회 batchSize가 올바르지 않습니다.")],
        ),
        (
            lambda: ReceiptRegistrationActivityQuery(
                user_ids=(_USER_ID,),
                target_date=_TARGET_DATE,
                limit=-1,
                recent_days=7,
            ),
            [("batchSize", "영수증 등록 활동 후보 조회 batchSize가 올바르지 않습니다.")],
        ),
        (
            lambda: ReceiptRegistrationActivityQuery(
                user_ids=(_USER_ID,),
                target_date=_TARGET_DATE,
                limit=10,
                recent_days=0,
            ),
            [("recentDays", "영수증 등록 활동 후보 조회 recentDays가 올바르지 않습니다.")],
        ),
        (
            lambda: ReceiptRegistrationActivityQuery(
                user_ids=(_USER_ID,),
                target_date=_TARGET_DATE,
                limit=10,
                recent_days=-1,
            ),
            [("recentDays", "영수증 등록 활동 후보 조회 recentDays가 올바르지 않습니다.")],
        ),
    ],
)
def test_candidate_queries_reject_malformed_inputs_with_domain_validation(
    make_query: _MalformedQueryFactory,
    expected_details: list[tuple[str, str]],
) -> None:
    with pytest.raises(ValidationError) as error:
        make_query()

    assert [(detail.field, detail.message) for detail in error.value.details] == expected_details


def test_scheduler_candidate_queries_do_not_raise_bare_value_error() -> None:
    tree = ast.parse(_RECEIPT_REPOSITORY.read_text())
    query_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in _SCHEDULER_CANDIDATE_QUERY_NAMES
    ]

    assert {node.name for node in query_classes} == _SCHEDULER_CANDIDATE_QUERY_NAMES
    for query_class in query_classes:
        for node in ast.walk(query_class):
            assert not (
                isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Call)
                and isinstance(node.exc.func, ast.Name)
                and node.exc.func.id == "ValueError"
            )
