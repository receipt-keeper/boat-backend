from uuid import UUID

from app.core.application.unit_of_work import UnitOfWork
from app.modules.users.application.commands.update_profile_image.command import (
    ClearProfileImageCommand,
    SetProfileImageCommand,
)
from app.modules.users.application.commands.update_profile_image.result import (
    UpdateProfileImageResult,
)
from app.modules.users.application.ports.profile_image_file_validator import (
    ProfileImageFileValidator,
)
from app.modules.users.application.ports.user_repository import UserRepository


class UpdateProfileImageCommandUseCase:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        profile_image_file_validator: ProfileImageFileValidator,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._user_repository = user_repository
        self._profile_image_file_validator = profile_image_file_validator
        self._unit_of_work = unit_of_work

    async def set_profile_image(
        self,
        command: SetProfileImageCommand,
    ) -> UpdateProfileImageResult:
        await self._profile_image_file_validator.ensure_owned_image_file(
            user_id=command.user_id,
            file_id=command.file_id,
        )
        profile_image_url = _profile_image_path(file_id=command.file_id)
        await self._user_repository.update_profile_image_url(
            user_id=command.user_id,
            profile_image_url=profile_image_url,
        )
        await self._unit_of_work.commit()
        return UpdateProfileImageResult(
            profile_image_url=profile_image_url,
        )

    async def clear_profile_image(
        self,
        command: ClearProfileImageCommand,
    ) -> None:
        await self._user_repository.update_profile_image_url(
            user_id=command.user_id,
            profile_image_url=None,
        )
        await self._unit_of_work.commit()


def _profile_image_path(*, file_id: UUID) -> str:
    return f"/files/{file_id}/content"
