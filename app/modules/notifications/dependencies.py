from collections.abc import Sequence
from typing import Annotated, cast

from fastapi import BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.event_dispatcher import EventDispatcher
from app.core.application.event_publisher import EventPublisher, NoOpEventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.core.config.dependencies import get_request_settings
from app.core.config.settings import Settings
from app.core.db.outbox.immediate_dispatch import dispatch_outbox_events_immediately
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.outbox.relay import OutboxRelay
from app.core.db.outbox.serialization import EventTypeRegistry
from app.core.db.session import AsyncSessionDep, request_session_factory
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
    """요청 반환 이후(BackgroundTasks) 또는 lifespan 폴러에서 실행되는 푸시 발송 진입점.

    호출 시점의 세션은 이미 닫혀 있거나(요청 스코프) 애초에 없으므로(폴러),
    실행 시점에 `session_factory`로 새 세션을 열어 저장소와 unit of work를 조립한다.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        push_sender: PushSender,
    ) -> None:
        self._session_factory = session_factory
        self._push_sender = push_sender

    async def dispatch(self, command: SendNotificationPushCommand) -> None:
        async with self._session_factory() as session:
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
    return NotificationPushDispatcher(
        session_factory=request_session_factory(request),
        push_sender=push_sender,
    )


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


def build_notification_event_registry() -> EventTypeRegistry:
    registry = EventTypeRegistry()
    registry.register(NotificationCreated)
    return registry


def build_notification_outbox_relay(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> OutboxRelay:
    """lifespan 폴러가 쓰는 relay를 조립한다.

    request가 없는 lifespan 컨텍스트이므로 `NotificationPushDispatcher`에는
    `session_factory`를 직접 주입한다. push sender는 요청 경로의
    `get_push_sender`와 동일한 규칙(`settings.push_send_enabled`)을 따른다.
    """
    push_sender: PushSender = (
        FcmPushSender.from_settings(settings)
        if settings.push_send_enabled
        else DisabledPushSender()
    )
    push_dispatcher = NotificationPushDispatcher(
        session_factory=session_factory,
        push_sender=push_sender,
    )
    registry = build_notification_event_registry()
    dispatcher = build_notification_event_dispatcher(push_dispatcher=push_dispatcher)
    return OutboxRelay(
        registry=registry,
        dispatcher=dispatcher,
        redeliver_after_seconds=settings.outbox_redeliver_after_seconds,
        max_retry=settings.outbox_max_retry,
        batch_size=settings.outbox_batch_size,
    )


class _ImmediateDispatchSchedulingPublisher(EventPublisher):
    """outbox insert(같은 세션) + 즉시 발행 스케줄링을 함께 수행하는 발행자.

    `publish()`는 주입된 `OutboxEventPublisher`로 같은 요청 세션에 insert만
    하고(commit은 use case가 소유), 이번 호출로 insert된 이벤트들의 event_id를
    BackgroundTasks 즉시 발행 태스크에 넘긴다. 그 태스크는 응답 반환 이후에야
    실행되므로, 원 요청 커밋이 실제로 성공했는지는 이 시점에 알 수 없다 -
    delete-then-dispatch(row가 없으면 skip)가 유령 발행을 막는다.
    """

    def __init__(
        self,
        *,
        outbox_publisher: OutboxEventPublisher,
        background_tasks: BackgroundTasks,
        request: Request,
        registry: EventTypeRegistry,
        dispatcher: EventDispatcher,
    ) -> None:
        self._outbox_publisher = outbox_publisher
        self._background_tasks = background_tasks
        self._request = request
        self._registry = registry
        self._dispatcher = dispatcher

    async def publish(self, events: Sequence[DomainEvent]) -> None:
        await self._outbox_publisher.publish(events)
        event_ids = [event.event_id for event in events]
        if not event_ids:
            return
        self._background_tasks.add_task(
            dispatch_outbox_events_immediately,
            request_session_factory(self._request),
            event_ids=event_ids,
            registry=self._registry,
            dispatcher=self._dispatcher,
        )


async def get_notification_event_publisher(
    session: AsyncSessionDep,
    background_tasks: BackgroundTasks,
    request: Request,
    push_dispatcher: Annotated[
        NotificationPushDispatcher,
        Depends(get_notification_push_dispatcher),
    ],
) -> EventPublisher:
    registry = build_notification_event_registry()
    dispatcher = build_notification_event_dispatcher(push_dispatcher=push_dispatcher)
    outbox_publisher = OutboxEventPublisher(session=session, registry=registry)
    return _ImmediateDispatchSchedulingPublisher(
        outbox_publisher=outbox_publisher,
        background_tasks=background_tasks,
        request=request,
        registry=registry,
        dispatcher=dispatcher,
    )


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


async def get_test_notification_create_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> CreateNotificationCommandUseCase:
    """이벤트 미발행 — example 테스트 보조용.

    example 모듈의 테스트 푸시 API가 표준 생성 경로(및 그에 연쇄되는
    background 푸시 발송)와 이중 발송되지 않도록, 이벤트를 발행하지 않는
    `NoOpEventPublisher`로 조립한 `CreateNotificationCommandUseCase`를
    제공한다. 표준 `POST /notifications` 경로에서는 사용하지 않는다.
    """
    return CreateNotificationCommandUseCase(
        notification_repository=notification_repository,
        unit_of_work=unit_of_work,
        event_publisher=NoOpEventPublisher(),
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
