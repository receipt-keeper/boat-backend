from collections.abc import Sequence
from typing import Annotated, cast

from fastapi import BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.event_dispatcher import EventDispatcher
from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.core.config.dependencies import get_request_settings
from app.core.config.settings import Settings
from app.core.db.session import AsyncSessionDep, request_async_session
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.events import DomainEvent
from app.modules.notifications.application.commands.create_notification.use_case import (
    CreateNotificationCommandUseCase,
)
from app.modules.notifications.application.commands.delete_user_push_tokens.use_case import (
    DeleteUserPushTokensCommandUseCase,
)
from app.modules.notifications.application.commands.mark_notification_read.use_case import (
    MarkNotificationReadCommandUseCase,
)
from app.modules.notifications.application.commands.register_device_token.use_case import (
    RegisterDeviceTokenCommandUseCase,
)
from app.modules.notifications.application.commands.send_notification_push.command import (
    SendNotificationPushCommand,
)
from app.modules.notifications.application.commands.send_notification_push.use_case import (
    SendNotificationPushCommandUseCase,
)
from app.modules.notifications.application.commands.unregister_device_token.use_case import (
    UnregisterDeviceTokenCommandUseCase,
)
from app.modules.notifications.application.commands.update_notification_settings.use_case import (
    UpdateNotificationSettingsCommandUseCase,
)
from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)
from app.modules.notifications.application.ports.push_sender import PushSender
from app.modules.notifications.application.ports.push_token_repository import (
    PushTokenRepository,
)
from app.modules.notifications.application.queries.get_notification_settings.use_case import (
    GetNotificationSettingsQueryUseCase,
)
from app.modules.notifications.application.queries.list_notifications.use_case import (
    ListNotificationsQueryUseCase,
)
from app.modules.notifications.domain.events import NotificationCreated
from app.modules.notifications.infrastructure.fcm.push_sender import (
    DisabledPushSender,
    FcmPushSender,
)
from app.modules.notifications.infrastructure.persistence.repository import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyPushTokenRepository,
)

SettingsDep = Annotated[Settings, Depends(get_request_settings)]


async def get_notification_repository(session: AsyncSessionDep) -> NotificationRepository:
    return SqlAlchemyNotificationRepository(session)


async def get_push_token_repository(session: AsyncSessionDep) -> PushTokenRepository:
    return SqlAlchemyPushTokenRepository(session)


async def get_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


async def get_push_sender(settings: SettingsDep) -> PushSender:
    if settings.push_send_enabled:
        return FcmPushSender.from_settings(settings)
    return DisabledPushSender()


class NotificationPushDispatcher:
    """응답 반환 이후(BackgroundTasks)에 실행되는 푸시 발송 진입점.

    요청 스코프 세션은 응답 시점에 닫히므로, 실행 시점에 새 세션을 열어
    저장소와 unit of work를 조립한다.
    """

    def __init__(self, *, request: Request, push_sender: PushSender) -> None:
        self._request = request
        self._push_sender = push_sender

    async def dispatch(self, command: SendNotificationPushCommand) -> None:
        async with request_async_session(self._request) as session:
            use_case = SendNotificationPushCommandUseCase(
                notification_repository=SqlAlchemyNotificationRepository(session),
                push_token_repository=SqlAlchemyPushTokenRepository(session),
                push_sender=self._push_sender,
                unit_of_work=SqlAlchemyUnitOfWork(session),
            )
            await use_case.execute(command)


async def get_notification_push_dispatcher(
    request: Request,
    push_sender: Annotated[PushSender, Depends(get_push_sender)],
) -> NotificationPushDispatcher:
    return NotificationPushDispatcher(request=request, push_sender=push_sender)


async def _handle_notification_created(
    event: NotificationCreated,
    *,
    push_dispatcher: NotificationPushDispatcher,
) -> None:
    await push_dispatcher.dispatch(
        SendNotificationPushCommand(
            user_id=event.user_id,
            notification_id=event.notification_id,
            message_type=event.message_type,
            kind=event.kind,
            title=event.title,
            message=event.message,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
        )
    )


def build_notification_event_dispatcher(
    *,
    push_dispatcher: NotificationPushDispatcher,
) -> EventDispatcher:
    async def handle_notification_created(event: DomainEvent) -> None:
        await _handle_notification_created(
            cast(NotificationCreated, event),
            push_dispatcher=push_dispatcher,
        )

    dispatcher = EventDispatcher()
    dispatcher.register(NotificationCreated, handle_notification_created)
    return dispatcher


class BackgroundEventPublisher(EventPublisher):
    """요청 응답 반환 이후(BackgroundTasks)에 이벤트를 디스패치하는 발행자.

    create use case는 이 port만 알고, FastAPI BackgroundTasks는 이 모듈 wiring
    계층(dependencies.py)까지만 노출된다.
    """

    def __init__(self, *, background_tasks: BackgroundTasks, dispatcher: EventDispatcher) -> None:
        self._background_tasks = background_tasks
        self._dispatcher = dispatcher

    async def publish(self, events: Sequence[DomainEvent]) -> None:
        self._background_tasks.add_task(self._dispatcher.dispatch, events)


async def get_notification_event_publisher(
    background_tasks: BackgroundTasks,
    push_dispatcher: Annotated[
        NotificationPushDispatcher,
        Depends(get_notification_push_dispatcher),
    ],
) -> EventPublisher:
    dispatcher = build_notification_event_dispatcher(push_dispatcher=push_dispatcher)
    return BackgroundEventPublisher(background_tasks=background_tasks, dispatcher=dispatcher)


def build_update_notification_settings_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> UpdateNotificationSettingsCommandUseCase:
    return UpdateNotificationSettingsCommandUseCase(
        notification_repository=SqlAlchemyNotificationRepository(session),
        unit_of_work=unit_of_work,
    )


def build_delete_user_push_tokens_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> DeleteUserPushTokensCommandUseCase:
    return DeleteUserPushTokensCommandUseCase(
        push_token_repository=SqlAlchemyPushTokenRepository(session),
        unit_of_work=unit_of_work,
    )


async def get_create_notification_command_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
    event_publisher: Annotated[EventPublisher, Depends(get_notification_event_publisher)],
) -> CreateNotificationCommandUseCase:
    return CreateNotificationCommandUseCase(
        notification_repository=notification_repository,
        unit_of_work=unit_of_work,
        event_publisher=event_publisher,
    )


async def get_mark_notification_read_command_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> MarkNotificationReadCommandUseCase:
    return MarkNotificationReadCommandUseCase(
        notification_repository=notification_repository,
        unit_of_work=unit_of_work,
    )


async def get_update_notification_settings_command_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> UpdateNotificationSettingsCommandUseCase:
    return UpdateNotificationSettingsCommandUseCase(
        notification_repository=notification_repository,
        unit_of_work=unit_of_work,
    )


async def get_list_notifications_query_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
) -> ListNotificationsQueryUseCase:
    return ListNotificationsQueryUseCase(notification_repository=notification_repository)


async def get_notification_settings_query_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
) -> GetNotificationSettingsQueryUseCase:
    return GetNotificationSettingsQueryUseCase(
        notification_repository=notification_repository,
    )


async def get_register_device_token_command_use_case(
    push_token_repository: Annotated[
        PushTokenRepository,
        Depends(get_push_token_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> RegisterDeviceTokenCommandUseCase:
    return RegisterDeviceTokenCommandUseCase(
        push_token_repository=push_token_repository,
        unit_of_work=unit_of_work,
    )


async def get_unregister_device_token_command_use_case(
    push_token_repository: Annotated[
        PushTokenRepository,
        Depends(get_push_token_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> UnregisterDeviceTokenCommandUseCase:
    return UnregisterDeviceTokenCommandUseCase(
        push_token_repository=push_token_repository,
        unit_of_work=unit_of_work,
    )


CreateNotificationCommandUseCaseDep = Annotated[
    CreateNotificationCommandUseCase,
    Depends(get_create_notification_command_use_case),
]
MarkNotificationReadCommandUseCaseDep = Annotated[
    MarkNotificationReadCommandUseCase,
    Depends(get_mark_notification_read_command_use_case),
]
UpdateNotificationSettingsCommandUseCaseDep = Annotated[
    UpdateNotificationSettingsCommandUseCase,
    Depends(get_update_notification_settings_command_use_case),
]
ListNotificationsQueryUseCaseDep = Annotated[
    ListNotificationsQueryUseCase,
    Depends(get_list_notifications_query_use_case),
]
GetNotificationSettingsQueryUseCaseDep = Annotated[
    GetNotificationSettingsQueryUseCase,
    Depends(get_notification_settings_query_use_case),
]
RegisterDeviceTokenCommandUseCaseDep = Annotated[
    RegisterDeviceTokenCommandUseCase,
    Depends(get_register_device_token_command_use_case),
]
UnregisterDeviceTokenCommandUseCaseDep = Annotated[
    UnregisterDeviceTokenCommandUseCase,
    Depends(get_unregister_device_token_command_use_case),
]
