from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExtractReceiptOcrCommand:
    user_id: UUID
    image_content: bytes
    content_type: str
