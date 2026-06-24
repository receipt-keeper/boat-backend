from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpenFileContentResult:
    content: bytes
    content_type: str
    size: int
