from app.core.domain.exceptions import DomainError, ErrorDetail, ValidationError

UNSUPPORTED_RECEIPT_MESSAGE = (
    "현재는 전자제품 영수증만 지원하고 있어요! 더 다양한 제품도 곧 보트랩에서 만나보실 수 있습니다."
)


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
    def __init__(
        self,
        *,
        file_indexes: tuple[int, ...],
        unreadable_file_indexes: tuple[int, ...] = (),
    ) -> None:
        if not file_indexes:
            raise ValueError("지원하지 않는 영수증 파일 인덱스가 최소 1개 필요합니다.")

        unsupported_indexes = set(file_indexes)
        unreadable_indexes = set(unreadable_file_indexes)
        if unsupported_indexes & unreadable_indexes:
            raise ValueError("동일한 파일을 지원 대상 아님과 인식 실패로 함께 처리할 수 없습니다.")

        self.unsupported_file_indexes = tuple(sorted(unsupported_indexes))
        self.unreadable_file_indexes = tuple(sorted(unreadable_indexes))
        self.file_indexes = tuple(sorted(unsupported_indexes | unreadable_indexes))
        super().__init__(UNSUPPORTED_RECEIPT_MESSAGE)


class ReceiptOcrProviderUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__("OCR 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
