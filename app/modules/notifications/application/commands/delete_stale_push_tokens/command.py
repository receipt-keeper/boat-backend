from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DeleteStalePushTokensCommand:
    older_than: datetime
