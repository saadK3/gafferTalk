import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from gaffertalk_api.domain.pro_research import ProDecisionReport
from gaffertalk_api.domain.recommendation_requests import NamedTransferResearchRequest
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.fpl.mapper import map_catalogue, map_fixtures
from gaffertalk_api.services.named_transfer_decisions import NamedTransferDecisionService
from gaffertalk_api.services.recommendation_loader import RecommendationLoader


class ProResearchLoader:
    """Load canonical FPL evidence and run the deterministic Pro decision service."""

    def __init__(
        self,
        client: FplClient,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._clock = clock
        self._service = NamedTransferDecisionService()

    async def named_transfer(
        self,
        request: NamedTransferResearchRequest,
    ) -> ProDecisionReport:
        bootstrap, raw_fixtures = await asyncio.gather(
            self._client.get_bootstrap(),
            self._client.get_fixtures(),
        )
        retrieved_at = self._clock()
        catalogue = map_catalogue(bootstrap, retrieved_at)
        fixtures = map_fixtures(raw_fixtures)
        if request.target_player_id not in catalogue.players:
            raise ValueError("the target player is not in the current FPL catalogue")
        snapshot, state = RecommendationLoader.build_state(
            request.squad,
            request.outgoing_player_id,
            request.outgoing_selling_price_tenths,
            catalogue,
        )
        evidence_ids = self._service.preview_evidence_ids(
            snapshot=snapshot,
            catalogue=catalogue,
            fixtures=fixtures,
            state=state,
            outgoing_player_id=request.outgoing_player_id,
            target_player_id=request.target_player_id,
        )
        summaries = await asyncio.gather(
            *(self._client.get_element_summary(player_id) for player_id in evidence_ids)
        )
        return self._service.research(
            squad_name=request.squad.name,
            snapshot=snapshot,
            catalogue=catalogue,
            fixtures=fixtures,
            state=state,
            outgoing_player_id=request.outgoing_player_id,
            target_player_id=request.target_player_id,
            histories=dict(zip(evidence_ids, summaries, strict=True)),
            created_at=self._clock(),
        )
