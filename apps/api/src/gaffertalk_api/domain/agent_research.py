from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from gaffertalk_api.domain.models import DomainModel, Player
from gaffertalk_api.domain.multi_gameweek_planning import (
    MultiGameweekRoute,
    MultiGameweekRouteReport,
)
from gaffertalk_api.domain.player_evidence import PlayerEvidenceReport
from gaffertalk_api.domain.recommendation_requests import CurrentSquadInput


class NamedTargetResearchRequest(DomainModel):
    """A natural-language target-player question with manager-confirmed state."""

    schema_version: Literal["1.0"] = "1.0"
    squad: CurrentSquadInput
    selling_prices_tenths: dict[int, int] = Field(default_factory=dict)
    protected_player_ids: tuple[int, ...] = ()
    horizon_gameweeks: int | None = Field(default=None, ge=1, le=2)
    maximum_points_hit: int | None = Field(default=None, ge=0, multiple_of=4)
    question: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def state_references_are_valid(self) -> "NamedTargetResearchRequest":
        squad_ids = set(self.squad.player_ids)
        if not set(self.selling_prices_tenths).issubset(squad_ids):
            raise ValueError("selling prices may only reference players in the confirmed squad")
        if any(price < 0 or price > 300 for price in self.selling_prices_tenths.values()):
            raise ValueError("every selling price must be between £0.0m and £30.0m")
        if len(set(self.protected_player_ids)) != len(self.protected_player_ids):
            raise ValueError("protected players must be unique")
        if not set(self.protected_player_ids).issubset(squad_ids):
            raise ValueError("protected players must belong to the confirmed squad")
        return self


class NamedTargetResearchStatus(StrEnum):
    RECOMMENDATION = "recommendation"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_SELLING_PRICES = "needs_selling_prices"
    TARGET_ALREADY_OWNED = "target_already_owned"
    NO_LEGAL_ROUTE = "no_legal_route"
    NO_ROUTE_FOUND_WITHIN_BOUNDS = "no_route_found_within_bounds"
    UNSUPPORTED = "unsupported"


class GroundedReason(DomainModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    text: str = Field(min_length=1)


class NamedTargetResearchReport(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    question: str = Field(min_length=1)
    created_at: datetime
    status: NamedTargetResearchStatus
    target: Player | None = None
    protected_players: tuple[Player, ...] = ()
    horizon_gameweek_ids: tuple[int, ...] = ()
    maximum_points_hit: int | None = None
    route_report: MultiGameweekRouteReport | None = None
    evidence: PlayerEvidenceReport | None = None
    recommended_route: MultiGameweekRoute | None = None
    provisional_route: MultiGameweekRoute | None = None
    alternatives: tuple[MultiGameweekRoute, ...] = Field(default=(), max_length=2)
    recommendation_reason: str = Field(min_length=1)
    alternative_reasons: tuple[str, ...] = ()
    strongest_objection: str = Field(min_length=1)
    change_conditions: tuple[str, ...] = Field(min_length=1)
    clarification_question: str | None = None
    grounded_reasons: tuple[GroundedReason, ...] = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def status_matches_routes(self) -> "NamedTargetResearchReport":
        if self.status is NamedTargetResearchStatus.RECOMMENDATION:
            if self.recommended_route is None or self.provisional_route is not None:
                raise ValueError("a recommendation report must contain an exact route")
        elif self.status is NamedTargetResearchStatus.NEEDS_SELLING_PRICES:
            if self.provisional_route is None or self.recommended_route is not None:
                raise ValueError("a provisional report must contain a provisional route")
        elif self.recommended_route is not None or self.provisional_route is not None:
            raise ValueError("this report status cannot contain a route")
        needs_clarification = self.status is NamedTargetResearchStatus.NEEDS_CLARIFICATION
        if needs_clarification != (self.clarification_question is not None):
            raise ValueError("clarification reports must contain exactly one question")
        return self


class NamedTargetResearchResponse(DomainModel):
    report: NamedTargetResearchReport
    assistant_message: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class NamedTargetSynthesisSelection(DomainModel):
    status: NamedTargetResearchStatus
    reason_ids: tuple[str, ...] = Field(min_length=1, max_length=4)
