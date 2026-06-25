from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UpdateProfileImageResult:
    profile_image_url: str | None
