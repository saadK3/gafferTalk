from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from gaffertalk_api.domain.models import DomainModel, Money, Player
from gaffertalk_api.domain.pro_research import (
    GroundedReason,
    PlayerEvidence,
    RiskPreference,
    SquadActionConfidence,
)


class RouteSearchStatus(StrEnum):
    NEEDS_SELLING_PRICES = "needs_selling_prices"
    ROUTE = "route"
    NO_LEGAL_ROUTE = "no_legal_route"


class RouteVerdict(StrEnum):
    RECOMMENDED = "recommended"
    DISCOURAGED = "discouraged"
    NO_ROUTE = "no_route"


class RouteTransfer(DomainModel):
    outgoing: Player
    incoming: Player
    confirmed_selling_price: Money | None = None


class TransferRouteCandidate(DomainModel):
    transfers: tuple[RouteTransfer, ...] = Field(min_length=1, max_length=2)
    budget_status: Literal["optimistic", "exact"]
    evidence_gain: float
    policy_adjusted_gain: float
    remaining_bank: Money
    free_transfers_used: int = Field(ge=0, le=2)
    free_transfers_after: int = Field(ge=0, le=5)
    points_hit: int = Field(ge=0, multiple_of=4)
    resulting_player_ids: tuple[int, ...] = Field(min_length=15, max_length=15)
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def route_is_distinct(self) -> "TransferRouteCandidate":
        outgoing = [transfer.outgoing.id for transfer in self.transfers]
        incoming = [transfer.incoming.id for transfer in self.transfers]
        if len(set(outgoing)) != len(outgoing) or len(set(incoming)) != len(incoming):
            raise ValueError("route transfers must use distinct outgoing and incoming players")
        return self


class RouteSearchConstraints(DomainModel):
    preserved_players: tuple[Player, ...] = ()
    excluded_players: tuple[Player, ...] = ()
    minimum_remaining_bank: Money = Money(tenths=0)
    maximum_transfers: Literal[1, 2] = 2


class RouteSearchStats(DomainModel):
    routes_examined: int = Field(ge=0)
    optimistic_routes: int = Field(ge=0)
    candidate_limit_per_position: int = Field(gt=0)
    elapsed_milliseconds: float = Field(ge=0)


class RouteResearchReport(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    decision_policy_version: Literal["1.0"] = "1.0"
    squad_name: str = Field(min_length=1)
    created_at: datetime
    data_retrieved_at: datetime
    risk_preference: RiskPreference
    target: Player
    constraints: RouteSearchConstraints
    status: RouteSearchStatus
    verdict: RouteVerdict
    manager_override: bool
    recommended_route: TransferRouteCandidate | None = None
    provisional_route: TransferRouteCandidate | None = None
    requested_selling_prices_for: tuple[Player, ...] = Field(max_length=2)
    alternatives: tuple[TransferRouteCandidate, ...] = Field(max_length=3)
    strategic_explanation: str = Field(min_length=1)
    opportunity_cost: str = Field(min_length=1)
    confidence: SquadActionConfidence
    evidence: tuple[PlayerEvidence, ...] = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    grounded_reasons: tuple[GroundedReason, ...] = Field(min_length=1)
    search_stats: RouteSearchStats

    @model_validator(mode="after")
    def status_matches_route(self) -> "RouteResearchReport":
        if self.status is RouteSearchStatus.NEEDS_SELLING_PRICES:
            if (
                self.provisional_route is None
                or self.recommended_route is not None
                or not self.requested_selling_prices_for
            ):
                raise ValueError("a provisional route must request its missing selling prices")
        elif self.status is RouteSearchStatus.ROUTE:
            if (
                self.recommended_route is None
                or self.recommended_route.budget_status != "exact"
                or self.provisional_route is not None
                or self.requested_selling_prices_for
            ):
                raise ValueError("a final route must be exact and need no selling prices")
        elif self.recommended_route is not None or self.provisional_route is not None:
            raise ValueError("a no-route report cannot contain a route")
        if (self.verdict is RouteVerdict.NO_ROUTE) != (
            self.status is RouteSearchStatus.NO_LEGAL_ROUTE
        ):
            raise ValueError("no-route verdict and no-legal-route status must appear together")
        return self


class RouteResearchResponse(DomainModel):
    report: RouteResearchReport
    assistant_message: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class RouteSynthesisSelection(DomainModel):
    status: RouteSearchStatus
    verdict: RouteVerdict
    reason_ids: tuple[str, ...] = Field(min_length=1, max_length=3)
