from typing import Protocol


class UnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class DeferredCommitUnitOfWork(UnitOfWork):
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None
