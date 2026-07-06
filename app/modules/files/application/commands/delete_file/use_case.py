from app.core.application.event_publisher import EventPublisher, NoOpEventPublisher
from app.core.application.unit_of_work import DeferredCommitUnitOfWork, UnitOfWork
from app.modules.files.application.commands.delete_file.command import DeleteFileCommand
from app.modules.files.application.ports.file_reference_guard import FileReferenceGuard
from app.modules.files.application.ports.file_repository import FileRepository
from app.modules.files.application.ports.object_storage import ObjectStorage
from app.modules.files.domain.exceptions import FileNotFoundError


class DeleteFileCommandUseCase:
    def __init__(
        self,
        repository: FileRepository,
        storage: ObjectStorage | None = None,
        unit_of_work: UnitOfWork | None = None,
        reference_guard: FileReferenceGuard | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._unit_of_work = unit_of_work or DeferredCommitUnitOfWork()
        self._reference_guard = reference_guard
        self._event_publisher = event_publisher or NoOpEventPublisher()

    async def execute(self, command: DeleteFileCommand) -> None:
        stored_files = await self._repository.find_all_by_id_for_user(
            file_id=command.file_id,
            user_id=command.user_id,
        )
        if not stored_files:
            raise FileNotFoundError(file_id=command.file_id)
        if self._reference_guard is not None:
            await self._reference_guard.ensure_not_referenced(file_id=command.file_id)
        if self._storage is not None:
            for stored_file in stored_files:
                await self._storage.delete(key=stored_file.file_object.storage_key.value)
        await self._repository.delete_by_id(file_id=command.file_id)
        file = stored_files[0].file
        file.record_deleted(
            storage_keys=[stored_file.file_object.storage_key.value for stored_file in stored_files]
        )
        events = file.pull_events()
        await self._event_publisher.publish(events)
        await self._unit_of_work.commit()
