"""Persist attempt reservations on the run ownership connection."""

from uuid import UUID

from email_support.models.research import ProviderUsage
from email_support.services.briefing_ownership import RunOwnership
from email_support.storage.postgres.persistence.briefing_runs import (
    complete_attempt,
    reserve_attempt,
)


class BriefingAttemptJournal:
    def __init__(self, owner: RunOwnership, limit: int) -> None:
        if limit < 1:
            raise ValueError("attempt limit must be positive")
        self._owner = owner
        self._limit = limit

    async def reserve(self, run_id: UUID, attempt_id: UUID, category: str) -> None:
        async with self._owner.transaction() as session:
            await reserve_attempt(session, run_id, attempt_id, self._limit, category)

    async def complete(
        self, run_id: UUID, attempt_id: UUID, outcome: str, usage: ProviderUsage | None
    ) -> None:
        async with self._owner.transaction() as session:
            await complete_attempt(session, run_id, attempt_id, outcome, usage)
