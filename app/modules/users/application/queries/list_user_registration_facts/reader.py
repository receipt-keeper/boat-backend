from abc import ABC, abstractmethod

from app.modules.users.application.queries.list_user_registration_facts.query import (
    ListUserRegistrationFactsQuery,
)
from app.modules.users.application.queries.list_user_registration_facts.result import (
    UserRegistrationFactsPage,
)


class UserRegistrationFactsReader(ABC):
    @abstractmethod
    async def list_registration_facts(
        self,
        *,
        query: ListUserRegistrationFactsQuery,
    ) -> UserRegistrationFactsPage:
        raise NotImplementedError
