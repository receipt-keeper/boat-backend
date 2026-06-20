from uuid import UUID

from app.modules.auth.application.ports.push_cleanup import PushCleanup


class NoOpPushCleanup(PushCleanup):
    """Temporary adapter while this repo has no persisted FCM token store."""

    async def cleanup_withdrawn_account(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> None:
        return None
