from datetime import date

import pytest

from app.modules.ocr.application.ports.receipt_ocr_client import ReceiptOcrImage
from app.modules.ocr.infrastructure.receipt_ocr_client import (
    OcrReceiptCategory,
    ReceiptOcrClient,
    ReceiptOcrStructuredOutput,
    ReceiptTransactionEvidence,
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


def test_structured_output_rejects_receipt_index_overlapping_failure_index() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        receipt_file_indexes=[0],
        unsupported_file_indexes=[0],
    )

    with pytest.raises(ValueError, match="지원 영수증과 실패 유형"):
        structured_output.to_extracted_fields(image_count=1)


def test_multimodal_prompt_separates_unsupported_receipts_from_unknown_devices() -> None:
    content = _build_openrouter_multimodal_content(
        images=(ReceiptOcrImage(file_index=0, content=b"receipt", content_type="image/png"),)
    )

    prompt = content[0]["text"]
    schema = ReceiptOcrStructuredOutput.model_json_schema()["properties"]

    assert isinstance(prompt, str)
    assert "At least one image must be an actual purchase receipt" in prompt
    assert "app launch or onboarding screens" in prompt
    assert "electronic-product text appears" in prompt
    assert "multiple independent transaction signals" in prompt
    assert "invoice without proof of completed payment" in prompt
    assert "restaurants or food" in prompt
    assert 'category "other_device"' in prompt
    assert "advertisements" in schema["unsupported_file_indexes"]["description"]
    assert (
        "actual paper or digital purchase receipt" in schema["receipt_file_indexes"]["description"]
    )
    evidence_schema = ReceiptOcrStructuredOutput.model_json_schema()["$defs"][
        "ReceiptTransactionEvidence"
    ]["properties"]
    assert "final total paid amount" in evidence_schema["total_paid"]["description"]
    assert "completed-transaction signal" in evidence_schema["completion_signal"]["description"]


def test_structured_output_keeps_unsupported_file_indexes() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        unsupported_file_indexes=[2, 1, 2],
    )

    extracted = structured_output.to_extracted_fields(image_count=3)

    assert extracted.unsupported_file_indexes == (1, 2)


def test_structured_output_keeps_supported_receipt_file_indexes() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        item_name="중소기업 전기히터 HBT-220",
        payment_location="전자제품 판매점",
        total_amount=129000,
        category=OcrReceiptCategory.OTHER_DEVICE,
        sub_category="기타",
        transaction_evidence=ReceiptTransactionEvidence(
            merchant=True,
            purchased_item=True,
            total_paid=True,
            completion_signal=True,
        ),
        receipt_file_indexes=[1, 0, 1],
    )

    extracted = structured_output.to_extracted_fields(image_count=2)

    assert extracted.receipt_file_indexes == (0, 1)
    assert extracted.unsupported_file_indexes == ()
    assert extracted.item_name == "중소기업 전기히터 HBT-220"


@pytest.mark.parametrize(
    "missing_evidence",
    ["merchant", "purchased_item", "total_paid", "completion_signal"],
)
def test_structured_output_downgrades_receipt_without_complete_transaction_evidence(
    missing_evidence: str,
) -> None:
    evidence = {
        "merchant": True,
        "purchased_item": True,
        "total_paid": True,
        "completion_signal": True,
    }
    evidence[missing_evidence] = False
    structured_output = ReceiptOcrStructuredOutput(
        item_name="일반 문서에 적힌 노트북",
        payment_location="일반 문서 작성 회사",
        total_amount=1000000,
        transaction_evidence=ReceiptTransactionEvidence(**evidence),
        receipt_file_indexes=[0],
    )

    extracted = structured_output.to_extracted_fields(image_count=1)

    assert extracted.receipt_file_indexes == ()
    assert extracted.unsupported_file_indexes == (0,)


def test_structured_output_combines_transaction_evidence_across_receipt_images() -> None:
    structured_output = ReceiptOcrStructuredOutput(
        item_name="노트북",
        payment_location="전자제품 판매점",
        total_amount=1000000,
        transaction_evidence=ReceiptTransactionEvidence(
            merchant=True,
            purchased_item=True,
            total_paid=True,
            completion_signal=True,
        ),
        receipt_file_indexes=[0, 1],
    )

    extracted = structured_output.to_extracted_fields(image_count=2)

    assert extracted.receipt_file_indexes == (0, 1)
    assert extracted.unsupported_file_indexes == ()


@pytest.mark.parametrize("missing_field", ["payment_location", "item_name", "total_amount"])
def test_structured_output_downgrades_receipt_without_visible_core_transaction_field(
    missing_field: str,
) -> None:
    fields: dict[str, str | int | None] = {
        "payment_location": "전자제품 판매점",
        "item_name": "노트북",
        "total_amount": 1000000,
    }
    fields[missing_field] = None
    structured_output = ReceiptOcrStructuredOutput(
        **fields,
        transaction_evidence=ReceiptTransactionEvidence(
            merchant=True,
            purchased_item=True,
            total_paid=True,
            completion_signal=True,
        ),
        receipt_file_indexes=[0],
    )

    extracted = structured_output.to_extracted_fields(image_count=1)

    assert extracted.receipt_file_indexes == ()
    assert extracted.unsupported_file_indexes == (0,)


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

    sub_category_schema = schema["sub_category"]["anyOf"][0]
    sub_category_values = sub_category_schema["enum"]
    assert sub_category_values == [
        "냉장고",
        "전자레인지",
        "밥솥",
        "정수기",
        "세탁기",
        "건조기",
        "청소기",
        "로봇청소기",
        "에어컨",
        "선풍기",
        "공기청정기",
        "가습기",
        "오븐",
        "데스크탑/TV",
        "게임기",
        "카메라",
        "스피커",
        "무선이어폰",
        "노트북",
        "헤드셋",
        "스마트워치",
        "핸드폰",
        "기타",
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
