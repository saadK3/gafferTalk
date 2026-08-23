import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from gaffertalk_api.domain.models import Money
from gaffertalk_api.domain.pro_research import ProDecisionReport, SquadActionReport
from gaffertalk_api.domain.recommendation_requests import (
    NamedTransferResearchRequest,
    RouteResearchRequest,
    SquadActionResearchRequest,
)
from gaffertalk_api.domain.route_research import RouteResearchReport
from gaffertalk_api.domain.transfers import TransferPlanningState
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.fpl.mapper import map_catalogue, map_fixtures
from gaffertalk_api.services.named_transfer_decisions import NamedTransferDecisionService
from gaffertalk_api.services.recommendation_loader import RecommendationLoader
from gaffertalk_api.services.route_research import RouteResearchService
from gaffertalk_api.services.squad_action_decisions import SquadActionDecisionService


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
        self._squad_action_service = SquadActionDecisionService()
        self._route_service = RouteResearchService()

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

    async def squad_action(self, request: SquadActionResearchRequest) -> SquadActionReport:
        bootstrap, raw_fixtures = await asyncio.gather(
            self._client.get_bootstrap(),
            self._client.get_fixtures(),
        )
        retrieved_at = self._clock()
        catalogue = map_catalogue(bootstrap, retrieved_at)
        fixtures = map_fixtures(raw_fixtures)
        snapshot = RecommendationLoader.build_snapshot(request.squad, catalogue)
        state = TransferPlanningState(
            bank=Money(tenths=request.squad.bank_tenths),
            free_transfers=request.squad.free_transfers,
            selling_prices={
                player_id: Money(tenths=price)
                for player_id, price in request.selling_prices_tenths.items()
            },
        )
        evidence_ids = self._squad_action_service.preview_evidence_ids(
            snapshot=snapshot,
            catalogue=catalogue,
            fixtures=fixtures,
            state=state,
            risk_preference=request.risk_preference,
        )
        summaries = await asyncio.gather(
            *(self._client.get_element_summary(player_id) for player_id in evidence_ids)
        )
        return self._squad_action_service.research(
            squad_name=request.squad.name,
            snapshot=snapshot,
            catalogue=catalogue,
            fixtures=fixtures,
            state=state,
            risk_preference=request.risk_preference,
            histories=dict(zip(evidence_ids, summaries, strict=True)),
            created_at=self._clock(),
        )

    async def route(self, request: RouteResearchRequest) -> RouteResearchReport:
        bootstrap, raw_fixtures = await asyncio.gather(
            self._client.get_bootstrap(),
            self._client.get_fixtures(),
        )
        retrieved_at = self._clock()
        catalogue = map_catalogue(bootstrap, retrieved_at)
        fixtures = map_fixtures(raw_fixtures)
        snapshot = RecommendationLoader.build_snapshot(request.squad, catalogue)
        state = TransferPlanningState(
            bank=Money(tenths=request.squad.bank_tenths),
            free_transfers=request.squad.free_transfers,
            selling_prices={
                player_id: Money(tenths=price)
                for player_id, price in request.selling_prices_tenths.items()
            },
        )
        purchase_prices = {
            player_id: Money(tenths=price)
            for player_id, price in request.purchase_prices_tenths.items()
        }
        evidence_ids = self._route_service.preview_evidence_ids(
            snapshot=snapshot,
            catalogue=catalogue,
            fixtures=fixtures,
            state=state,
            target_player_id=request.target_player_id,
            preserved_player_ids=request.preserved_player_ids,
            excluded_player_ids=request.excluded_player_ids,
            minimum_remaining_bank=Money(tenths=request.minimum_remaining_bank_tenths),
            maximum_transfers=request.maximum_transfers,
            risk_preference=request.risk_preference,
            purchase_prices=purchase_prices,
        )
        summaries = await asyncio.gather(
            *(self._client.get_element_summary(player_id) for player_id in evidence_ids)
        )
        return self._route_service.research(
            squad_name=request.squad.name,
            snapshot=snapshot,
            catalogue=catalogue,
            fixtures=fixtures,
            state=state,
            target_player_id=request.target_player_id,
            preserved_player_ids=request.preserved_player_ids,
            excluded_player_ids=request.excluded_player_ids,
            minimum_remaining_bank=Money(tenths=request.minimum_remaining_bank_tenths),
            maximum_transfers=request.maximum_transfers,
            risk_preference=request.risk_preference,
            proceed_if_discouraged=request.proceed_if_discouraged,
            purchase_prices=purchase_prices,
            histories=dict(zip(evidence_ids, summaries, strict=True)),
            created_at=self._clock(),
        )
