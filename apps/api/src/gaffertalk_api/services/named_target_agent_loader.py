import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from gaffertalk_api.domain.agent_research import (
    NamedTargetResearchReport,
    NamedTargetResearchRequest,
)
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.services.named_target_agent import NamedTargetAgentService
from gaffertalk_api.services.player_evidence_loader import PlayerEvidenceLoader


class NamedTargetAgentLoader:
    """Load official FPL data and run the bounded named-target research loop."""

    def __init__(
        self,
        client: FplClient,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._clock = clock
        self._service = NamedTargetAgentService()
        self._evidence_loader = PlayerEvidenceLoader(client, clock=clock)

    async def research(self, request: NamedTargetResearchRequest) -> NamedTargetResearchReport:
        created_at = self._clock()
        if not self._service.has_named_target_intent(request.question):
            return self._service.unsupported_report(request=request, created_at=created_at)
        bootstrap, fixtures = await asyncio.gather(
            self._client.get_bootstrap_observation(),
            self._client.get_fixtures_observation(),
        )
        return await self._service.research(
            request=request,
            bootstrap=bootstrap,
            fixtures=fixtures,
            evidence_loader=self._evidence_loader,
            created_at=created_at,
        )
