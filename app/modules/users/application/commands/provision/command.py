from dataclasses import dataclass


@dataclass(frozen=True)
class ProvisionUserCommand:
    name: str | None
    email: str | None
