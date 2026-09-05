import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from gaffertalk_api.domain.player_evidence import (
    PlayerEvidenceReport,
    PlayerEvidenceRequest,
)
from gaffertalk_api.integrations.fpl.client import FplClient, FplObservation
from gaffertalk_api.integrations.fpl.schemas import FplElementSummary
from gaffertalk_api.services.player_evidence import PlayerEvidenceService


class PlayerEvidenceLoader:
    """Load the minimum official FPL sources needed for a player evidence report."""

    def __init__(
        self,
        client: FplClient,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._clock = clock
        self._service = PlayerEvidenceService()

    async def load(self, request: PlayerEvidenceRequest) -> PlayerEvidenceReport:
        bootstrap, fixtures = await asyncio.gather(
            self._client.get_bootstrap_observation(),
            self._client.get_fixtures_observation(),
        )
        available_ids = {player.id for player in bootstrap.value.elements}
        unknown = set(request.player_ids) - available_ids
        if unknown:
            raise ValueError(f"players are not in the current FPL catalogue: {sorted(unknown)}")

        results = await asyncio.gather(
            *(
                self._client.get_element_summary_observation(player_id)
                for player_id in request.player_ids
            ),
            return_exceptions=True,
        )
        summaries: dict[int, FplObservation[FplElementSummary] | None] = {}
        for player_id, result in zip(request.player_ids, results, strict=True):
            summaries[player_id] = None if isinstance(result, BaseException) else result
        return self._service.build(
            request=request,
            bootstrap=bootstrap,
            fixtures=fixtures,
            summaries=summaries,
            generated_at=self._clock(),
        )

