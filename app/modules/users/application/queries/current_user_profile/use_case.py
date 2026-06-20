from app.core.domain.exceptions import NotFoundError
from app.modules.users.application.ports.user_repository import UserAccountState, UserRepository
from app.modules.users.application.queries.current_user_profile.query import CurrentUserProfileQuery
from app.modules.users.application.queries.current_user_profile.result import (
    CurrentUserProfileResult,
)


class CurrentUserProfileQueryUseCase:
    def __init__(self, *, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def execute(self, query: CurrentUserProfileQuery) -> CurrentUserProfileResult:
        state = await self._user_repository.find_account_state(user_id=query.user_id)
        if state is None:
            raise NotFoundError("사용자를 찾을 수 없습니다.")
        return _profile_result(state)


def _profile_result(state: UserAccountState) -> CurrentUserProfileResult:
    normalized_email = (
        None if state.user.normalized_email is None else state.user.normalized_email.value
    )
    return CurrentUserProfileResult(
        user_id=state.user.id,
        email=state.user.email,
        normalized_email=normalized_email,
        name=state.user.name,
        nickname=state.user.nickname,
        profile_image_url=state.user.profile_image_url,
        notification_enabled=state.settings.notification_enabled,
        marketing_consent=state.settings.marketing_consent,
        free_analysis_tokens_remaining=state.entitlement.free_analysis_tokens_remaining.value,
        push_token_count=len(state.push_tokens),
    )
