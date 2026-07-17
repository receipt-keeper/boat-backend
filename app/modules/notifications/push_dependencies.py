from collections.abc import Sequence
from typing import Annotated, cast

from fastapi import BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.event_dispatcher import EventDispatcher
from app.core.application.event_publisher import EventPublisher
from app.core.config.dependencies import get_request_settings
from app.core.config.settings import Settings
from app.core.db.outbox.immediate_dispatch import dispatch_outbox_events_immediately
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.outbox.relay import OutboxRelay
from app.core.db.outbox.serialization import EventTypeRegistry
from app.core.db.session import AsyncSessionDep, request_session_factory
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.events import DomainEvent
from app.modules.notifications.application.commands.send_notification_push.command import (
    SendNotificationPushCommand,
)
from app.modules.notifications.application.commands.send_notification_push.use_case import (
    SendNotificationPushCommandUseCase,
)
from app.modules.notifications.application.ports.push_sender import PushSender
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


async def get_push_sender(settings: SettingsDep) -> PushSender:
    if settings.push_send_enabled:
        return FcmPushSender.from_settings(settings)
    return DisabledPushSender()


class NotificationPushDispatcher:
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
            category=event.category,
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
    registry: EventTypeRegistry,
) -> OutboxRelay:
    push_sender: PushSender = (
        FcmPushSender.from_settings(settings)
        if settings.push_send_enabled
        else DisabledPushSender()
    )
    push_dispatcher = NotificationPushDispatcher(
        session_factory=session_factory,
        push_sender=push_sender,
    )
    dispatcher = build_notification_event_dispatcher(push_dispatcher=push_dispatcher)
    return OutboxRelay(
        registry=registry,
        dispatcher=dispatcher,
        redeliver_after_seconds=settings.outbox_redeliver_after_seconds,
        max_retry=settings.outbox_max_retry,
        batch_size=settings.outbox_batch_size,
    )


class _ImmediateDispatchSchedulingPublisher(EventPublisher):
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
