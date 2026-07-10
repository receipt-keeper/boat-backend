import base64
import json
from uuid import UUID

import pytest

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.receipts.domain.value_objects import ReceiptSort
from app.modules.receipts.infrastructure.persistence.listing import decode_cursor


def test_decode_cursor_rejects_cursor_for_different_sort() -> None:
    payload = {
        "sort": "recent",
        "value": "2026-06-29T00:00:00+00:00",
        "id": str(UUID("00000000-0000-0000-0000-000000000201")),
    }
    cursor = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")

    with pytest.raises(ValidationError) as exc_info:
        decode_cursor(cursor.rstrip("="), sort=ReceiptSort.EXPIRES_ON)

    assert exc_info.value.details == [
        ErrorDetail(field="cursor", message="유효하지 않은 커서입니다.")
    ]
