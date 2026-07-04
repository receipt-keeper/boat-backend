from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeleteStalePushTokensResult:
    deleted_count: int
