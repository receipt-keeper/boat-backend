import pytest

from app.modules.ocr.application.ports.receipt_ocr_client import ReceiptOcrImage
from app.modules.ocr.infrastructure.receipt_ocr_client import (
    ReceiptOcrStructuredOutput,
    _build_openrouter_multimodal_content,
)


def test_openrouter_multimodal_content_keeps_image_order_and_indexes() -> None:
    content = _build_openrouter_multimodal_content(
        images=(
            ReceiptOcrImage(file_index=0, content=b"first", content_type="image/png"),
            ReceiptOcrImage(file_index=1, content=b"second", content_type="image/jpeg"),
        )
    )

    assert content[1] == {"type": "text", "text": "IMAGE_INDEX: 0"}
    assert content[2] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,Zmlyc3Q="},
    }
    assert content[3] == {"type": "text", "text": "IMAGE_INDEX: 1"}
    assert content[4] == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,c2Vjb25k"},
    }


def test_structured_output_rejects_file_index_outside_request_range() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        item_name="삼성 냉장고",
        unreadable_file_indexes=[2],
    )

    with pytest.raises(ValueError, match="요청 범위를 벗어난 이미지 인덱스"):
        structured_output.to_extracted_fields(image_count=2)
