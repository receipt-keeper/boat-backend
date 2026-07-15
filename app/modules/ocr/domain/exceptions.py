from app.core.domain.exceptions import DomainError, ErrorDetail, ValidationError


class ReceiptImageUnreadableError(ValidationError):
    def __init__(self, *, file_indexes: tuple[int, ...]) -> None:
        if not file_indexes:
            raise ValueError("인식 실패 파일 인덱스가 최소 1개 필요합니다.")

        self.file_indexes = tuple(sorted(set(file_indexes)))
        message = "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요."
        super().__init__(
            [
                ErrorDetail(
                    field="file",
                    message=message,
                )
            ]
        )


class UnsupportedReceiptError(DomainError):
    def __init__(self, *, file_indexes: tuple[int, ...]) -> None:
        if not file_indexes:
            raise ValueError("지원하지 않는 영수증 파일 인덱스가 최소 1개 필요합니다.")

        self.file_indexes = tuple(sorted(set(file_indexes)))
        super().__init__("가전·전자·IT 기기 관련 영수증만 분석할 수 있습니다.")


class ReceiptOcrProviderUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__("OCR 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
