from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentPrincipalQuery:
    token: str
