from typing import Final

from app.modules.files.api.upload_validation import UploadValidationPolicy

RECEIPT_OCR_UPLOAD_POLICY: Final = UploadValidationPolicy(
    allowed_content_types=(
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
    ),
    max_upload_bytes=10_485_760,
    max_upload_count=1,
)
