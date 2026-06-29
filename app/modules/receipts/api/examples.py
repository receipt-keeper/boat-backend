from typing import Final

from fastapi import status

SAMPLE_RECEIPT_FILE_ID: Final = "00000000-0000-0000-0000-000000000201"

CREATE_RECEIPT_REQUEST_EXAMPLES: Final = [
    {
        "item_name": "삼성 냉장고 875L",
        "brand_name": "삼성",
        "payment_location": "전자랜드",
        "payment_date": "2026-06-29",
        "total_amount": 1200000,
        "period_months": 24,
        "category": "가전",
        "memo": "앱 연동 테스트",
        "requires_physical_receipt": True,
        "receipt_file_ids": [SAMPLE_RECEIPT_FILE_ID],
    },
    {
        "item_name": "병원 진료비",
        "brand_name": None,
        "payment_location": "나나동물병원",
        "payment_date": "2026-06-20",
        "total_amount": None,
        "period_months": None,
        "category": "의료",
        "memo": "OCR 실패 후 수동 입력 테스트",
        "requires_physical_receipt": True,
        "receipt_file_ids": ["00000000-0000-0000-0000-000000000202"],
    },
]

CREATE_RECEIPT_REQUEST_OPENAPI_EXAMPLES: Final = {
    "ocr_reviewed": {
        "summary": "OCR 후보값 확인 후 등록",
        "value": CREATE_RECEIPT_REQUEST_EXAMPLES[0],
    },
    "manual_nullable": {
        "summary": "OCR 실패 후 수동 입력",
        "value": CREATE_RECEIPT_REQUEST_EXAMPLES[1],
    },
}

UPDATE_RECEIPT_REQUEST_EXAMPLES: Final = [
    {
        "item_name": "삼성 냉장고 900L",
        "brand_name": "삼성",
        "payment_location": None,
        "payment_date": "2026-06-29",
        "total_amount": None,
        "period_months": 36,
        "category": "주방 가전",
        "memo": "사용자 수정값 저장 테스트",
        "requires_physical_receipt": True,
        "receipt_file_ids": [SAMPLE_RECEIPT_FILE_ID],
    }
]

UPDATE_RECEIPT_REQUEST_OPENAPI_EXAMPLES: Final = {
    "partial_update": {
        "summary": "사용자 수정값 저장",
        "value": UPDATE_RECEIPT_REQUEST_EXAMPLES[0],
    }
}

RECEIPT_RESPONSE_EXAMPLE: Final = {
    "receiptId": "00000000-0000-0000-0000-000000000301",
    "itemName": "삼성 냉장고 875L",
    "brandName": "삼성",
    "paymentLocation": "전자랜드",
    "paymentDate": "2026-06-29",
    "totalAmount": 1200000,
    "periodMonths": 24,
    "expiresOn": "2028-06-29",
    "category": "가전",
    "memo": "앱 연동 테스트",
    "requiresPhysicalReceipt": True,
    "receiptFileIds": [SAMPLE_RECEIPT_FILE_ID],
    "imageUrl": None,
    "warrantyDDay": 731,
    "serialNumber": None,
    "supportUrl": None,
    "registeredAt": "2026-06-29T12:00:00",
}

UPDATED_RECEIPT_RESPONSE_EXAMPLE: Final = {
    **RECEIPT_RESPONSE_EXAMPLE,
    "itemName": "삼성 냉장고 900L",
    "paymentLocation": None,
    "totalAmount": None,
    "periodMonths": 36,
    "expiresOn": "2029-06-29",
    "category": "주방 가전",
    "memo": "사용자 수정값 저장 테스트",
}

RECEIPT_LIST_RESPONSE_EXAMPLE: Final = {
    "success": True,
    "status": status.HTTP_200_OK,
    "data": {
        "receipts": [RECEIPT_RESPONSE_EXAMPLE],
        "totalCount": 1,
        "pagination": {
            "nextCursor": None,
            "hasNext": False,
            "limit": 20,
            "totalCount": 1,
        },
    },
}

EMPTY_RECEIPT_LIST_RESPONSE_EXAMPLE: Final = {
    "success": True,
    "status": status.HTTP_200_OK,
    "data": {
        "receipts": [],
        "totalCount": 0,
        "pagination": {
            "nextCursor": None,
            "hasNext": False,
            "limit": 20,
            "totalCount": 0,
        },
    },
}

CREATE_RECEIPT_RESPONSE_EXAMPLE: Final = {
    "success": True,
    "status": status.HTTP_201_CREATED,
    "data": RECEIPT_RESPONSE_EXAMPLE,
}

GET_RECEIPT_RESPONSE_EXAMPLE: Final = {
    "success": True,
    "status": status.HTTP_200_OK,
    "data": RECEIPT_RESPONSE_EXAMPLE,
}

UPDATE_RECEIPT_RESPONSE_EXAMPLE: Final = {
    "success": True,
    "status": status.HTTP_200_OK,
    "data": UPDATED_RECEIPT_RESPONSE_EXAMPLE,
}

DELETE_RECEIPT_RESPONSE_EXAMPLE: Final = {
    "success": True,
    "status": status.HTTP_200_OK,
    "data": None,
}
