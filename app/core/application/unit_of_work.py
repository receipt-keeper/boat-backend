from collections.abc import Awaitable, Callable
from typing import Protocol


class UnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class DeferredCommitUnitOfWork(UnitOfWork):
    def __init__(self, rollback: Callable[[], Awaitable[None]] | None = None) -> None:
        self._rollback = rollback

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        if self._rollback is not None:
            await self._rollback()
        return None
