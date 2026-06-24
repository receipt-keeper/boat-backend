from app.core.domain.exceptions import DomainError, ErrorDetail, ValidationError


class ReceiptImageUnreadableError(ValidationError):
    def __init__(self) -> None:
        message = "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요."
        super().__init__(
            [
                ErrorDetail(
                    field="image_uri",
                    message=message,
                )
            ]
        )


class ReceiptOcrProviderUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__("OCR 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
