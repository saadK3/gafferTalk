import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from gaffertalk_api.domain.errors import (
    InvalidTeamIdError,
    InvalidUpstreamFplResponseError,
    UpstreamFplNotFoundError,
)
from gaffertalk_api.domain.models import (
    Gameweek,
    SquadAvailability,
    SquadAvailabilityStatus,
    SquadLookupResult,
)
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.fpl.mapper import (
    map_catalogue,
    map_entry,
    map_squad_snapshot,
)


class TeamLoader:
    """Load the latest public, deadline-finalized squad for an FPL entry."""

    def __init__(
        self,
        client: FplClient,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._clock = clock

    async def load(self, team_id: int) -> SquadLookupResult:
        if team_id <= 0:
            raise InvalidTeamIdError(team_id)

        retrieved_at = self._clock()
        try:
            entry_payload, bootstrap = await asyncio.gather(
                self._client.get_entry(team_id),
                self._client.get_bootstrap(),
            )
        except UpstreamFplNotFoundError as error:
            if error.resource == f"entry/{team_id}/":
                raise InvalidTeamIdError(team_id) from error
            raise

        try:
            entry = map_entry(entry_payload)
            catalogue = map_catalogue(bootstrap, retrieved_at)
        except ValidationError as error:
            raise InvalidUpstreamFplResponseError(
                "FPL data could not be mapped into the canonical domain"
            ) from error
        published_candidates = sorted(
            (
                gameweek
                for gameweek in catalogue.gameweeks
                if gameweek.deadline_time <= retrieved_at
                and gameweek.id >= entry.started_gameweek_id
            ),
            key=lambda gameweek: gameweek.id,
            reverse=True,
        )

        for gameweek in published_candidates:
            try:
                picks = await self._client.get_picks(team_id, gameweek.id)
            except UpstreamFplNotFoundError:
                continue
            try:
                snapshot = map_squad_snapshot(picks, gameweek, catalogue, retrieved_at)
            except ValidationError as error:
                raise InvalidUpstreamFplResponseError(
                    "FPL picks could not be mapped into a canonical squad"
                ) from error
            return SquadLookupResult(
                entry=entry,
                availability=SquadAvailability(
                    status=SquadAvailabilityStatus.AVAILABLE,
                    reason=f"Finalized {gameweek.name} squad is publicly available.",
                    next_deadline=self._next_deadline(catalogue.gameweeks, retrieved_at),
                ),
                snapshot=snapshot,
                retrieved_at=retrieved_at,
            )

        return SquadLookupResult(
            entry=entry,
            availability=SquadAvailability(
                status=SquadAvailabilityStatus.NOT_YET_PUBLISHED,
                reason="No deadline-finalized squad is publicly available for this entry yet.",
                next_deadline=self._next_deadline(catalogue.gameweeks, retrieved_at),
            ),
            snapshot=None,
            retrieved_at=retrieved_at,
        )

    @staticmethod
    def _next_deadline(
        gameweeks: tuple[Gameweek, ...],
        now: datetime,
    ) -> datetime | None:
        deadlines = sorted(
            gameweek.deadline_time for gameweek in gameweeks if gameweek.deadline_time > now
        )
        return deadlines[0] if deadlines else None
