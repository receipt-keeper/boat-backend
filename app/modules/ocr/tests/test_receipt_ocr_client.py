from datetime import date

import pytest

from app.modules.ocr.application.ports.receipt_ocr_client import ReceiptOcrImage
from app.modules.ocr.infrastructure.receipt_ocr_client import (
    OcrReceiptCategory,
    ReceiptOcrClient,
    ReceiptOcrStructuredOutput,
    _build_openrouter_multimodal_content,
)
from app.modules.receipts.domain.value_objects import ReceiptCategory


@pytest.mark.asyncio
async def test_mock_receipt_ocr_client_rejects_empty_images() -> None:
    client = ReceiptOcrClient()

    with pytest.raises(ValueError, match="OCR 분석 이미지가 최소 1개 필요합니다"):
        await client.extract(images=())


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


def test_structured_output_rejects_unsupported_file_index_outside_request_range() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        unsupported_file_indexes=[2],
    )

    with pytest.raises(ValueError, match="요청 범위를 벗어난 이미지 인덱스"):
        structured_output.to_extracted_fields(image_count=2)


def test_structured_output_rejects_overlapping_failure_indexes() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        unreadable_file_indexes=[0],
        unsupported_file_indexes=[0],
    )

    with pytest.raises(ValueError, match="동일한 이미지를 두 실패 유형"):
        structured_output.to_extracted_fields(image_count=1)


def test_multimodal_prompt_separates_unsupported_receipts_from_unknown_devices() -> None:
    content = _build_openrouter_multimodal_content(
        images=(ReceiptOcrImage(file_index=0, content=b"receipt", content_type="image/png"),)
    )

    prompt = content[0]["text"]
    schema = ReceiptOcrStructuredOutput.model_json_schema()["properties"]

    assert isinstance(prompt, str)
    assert "supports only receipts" in prompt
    assert "restaurants or food" in prompt
    assert 'category "other_device"' in prompt
    assert "food, restaurants" in schema["unsupported_file_indexes"]["description"]


def test_structured_output_keeps_unsupported_file_indexes() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        unsupported_file_indexes=[2, 1, 2],
    )

    extracted = structured_output.to_extracted_fields(image_count=3)

    assert extracted.unsupported_file_indexes == (1, 2)


def test_multimodal_prompt_extracts_explicit_serial_number_from_any_image() -> None:
    content = _build_openrouter_multimodal_content(
        images=(
            ReceiptOcrImage(file_index=0, content=b"receipt", content_type="image/png"),
            ReceiptOcrImage(file_index=1, content=b"label", content_type="image/png"),
        )
    )

    prompt = content[0]["text"]

    assert isinstance(prompt, str)
    assert "Extract serial_number from any input image" in prompt
    assert '"S/N"' in prompt
    assert "Do not use an order number" in prompt


def test_structured_output_keeps_explicit_serial_number() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        item_name="Apple iPhone",
        serial_number=" F2LX1234ABCD ",
    )

    extracted = structured_output.to_extracted_fields(image_count=2)

    assert extracted.serial_number == "F2LX1234ABCD"

    schema = ReceiptOcrStructuredOutput.model_json_schema()["properties"]
    assert "in any input image" in schema["serial_number"]["description"]
    assert "cannot be classified" in schema["unreadable_file_indexes"]["description"]


def test_structured_output_keeps_explicit_expiration_date() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        item_name="Apple iPhone",
        expires_on=date(2027, 9, 30),
    )

    extracted = structured_output.to_extracted_fields(image_count=1)

    assert extracted.expires_on == date(2027, 9, 30)

    schema = ReceiptOcrStructuredOutput.model_json_schema()["properties"]
    assert "Do not calculate or guess" in schema["expires_on"]["description"]


def test_structured_output_uses_english_category_enum_and_korean_api_label() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        item_name="Apple iPhone",
        category=OcrReceiptCategory.IT_DEVICE,
        sub_category="핸드폰",
    )

    extracted = structured_output.to_extracted_fields(image_count=1)
    schema = ReceiptOcrStructuredOutput.model_json_schema()["properties"]
    category_schema = schema["category"]["anyOf"][0]
    enum_reference = category_schema["$ref"].split("/")[-1]
    category_values = ReceiptOcrStructuredOutput.model_json_schema()["$defs"][enum_reference][
        "enum"
    ]

    assert extracted.category == "IT 기기"
    assert category_values == [
        "kitchen_appliance",
        "laundry_cleaning",
        "living_climate",
        "it_device",
        "other_device",
    ]


def test_ocr_and_receipt_categories_share_the_same_api_labels() -> None:
    assert {category.value: category.api_label for category in OcrReceiptCategory} == {
        category.value: category.api_label for category in ReceiptCategory
    }


def test_multimodal_prompt_classifies_coverage_by_covered_device() -> None:
    content = _build_openrouter_multimodal_content(
        images=(ReceiptOcrImage(file_index=0, content=b"applecare", content_type="image/png"),)
    )

    prompt = content[0]["text"]

    assert isinstance(prompt, str)
    assert "classify category and" in prompt
    assert "by the covered device" in prompt
    assert "Do not calculate or guess expires_on" in prompt
