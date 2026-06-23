from app.core.application.unit_of_work import UnitOfWork


class FakeUnitOfWork(UnitOfWork):
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1
