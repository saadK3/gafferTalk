import asyncio
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime

from gaffertalk_api.domain.models import SquadAvailabilityStatus
from gaffertalk_api.domain.pro_plans import PlanEvidenceContext
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.fpl.mapper import map_catalogue, map_fixtures
from gaffertalk_api.services.team_loader import TeamLoader


class ProPlanLoader:
    """Load the public snapshot, availability and fixture schedule used by plans."""

    def __init__(
        self,
        client: FplClient,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._clock = clock
        self._team_loader = TeamLoader(client, clock=clock)

    async def load(self, team_id: int) -> PlanEvidenceContext:
        lookup, bootstrap, raw_fixtures = await asyncio.gather(
            self._team_loader.load(team_id),
            self._client.get_bootstrap(),
            self._client.get_fixtures(),
        )
        retrieved_at = self._clock()
        if (
            lookup.availability.status is not SquadAvailabilityStatus.AVAILABLE
            or lookup.snapshot is None
        ):
            raise ValueError("A finalized public FPL snapshot is required to build a plan.")
        catalogue = map_catalogue(bootstrap, retrieved_at)
        fixtures = map_fixtures(raw_fixtures)
        future_gameweeks = tuple(
            gameweek for gameweek in catalogue.gameweeks if gameweek.deadline_time > retrieved_at
        )
        if len(future_gameweeks) < 3:
            raise ValueError("Fewer than three future Gameweeks remain; a 3GW plan is unavailable.")
        horizon = tuple(gameweek.id for gameweek in future_gameweeks[:3])
        evidence_gameweeks = tuple(gameweek.id for gameweek in future_gameweeks[:5])
        signature_rows = [
            {
                "id": fixture.id,
                "gameweek": fixture.gameweek_id,
                "kickoff": fixture.kickoff_time.isoformat() if fixture.kickoff_time else None,
                "home": fixture.home_club_id,
                "away": fixture.away_club_id,
                "home_difficulty": fixture.home_difficulty,
                "away_difficulty": fixture.away_difficulty,
            }
            for fixture in fixtures
            if fixture.gameweek_id in evidence_gameweeks
        ]
        fixture_signature = hashlib.sha256(
            json.dumps(signature_rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        snapshot_players = tuple(pick.player.id for pick in lookup.snapshot.picks)
        return PlanEvidenceContext(
            retrieved_at=retrieved_at,
            horizon_gameweeks=horizon,  # type: ignore[arg-type]
            evidence_gameweeks=evidence_gameweeks,
            deadlines={gameweek.id: gameweek.deadline_time for gameweek in future_gameweeks[:5]},
            fixture_signature=fixture_signature,
            player_statuses={player.id: player.status for player in catalogue.players.values()},
            player_chances={
                player.id: player.chance_of_playing_next_round
                for player in catalogue.players.values()
            },
            public_snapshot_gameweek=lookup.snapshot.gameweek.id,
            public_player_ids=snapshot_players,
        )
