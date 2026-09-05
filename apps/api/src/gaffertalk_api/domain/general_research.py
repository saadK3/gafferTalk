from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from gaffertalk_api.domain.agent_research import (
    GroundedReason,
    NamedTargetResearchReport,
)
from gaffertalk_api.domain.models import DomainModel, Player
from gaffertalk_api.domain.multi_gameweek_planning import MultiGameweekRouteReport
from gaffertalk_api.domain.player_evidence import (
    EvidenceNature,
    PlayerEvidenceReport,
)
from gaffertalk_api.domain.pro_research import RiskPreference, SquadActionReport
from gaffertalk_api.domain.recommendation_requests import CurrentSquadInput


class ResearchCapability(StrEnum):
    NAMED_TARGET_TRANSFER = "named_target_transfer"
    HISTORICAL_ALTERNATIVES = "historical_alternatives"
    BUDGET_RELEASE = "budget_release"
    HOLD_OR_TRANSFER = "hold_or_transfer"
    SQUAD_CONCERNS = "squad_concerns"
    UNSUPPORTED = "unsupported"


class GeneralResearchStatus(StrEnum):
    RECOMMENDATION = "recommendation"
    INFORMATION = "information"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_SELLING_PRICES = "needs_selling_prices"
    NO_ROUTE = "no_route"
    UNSUPPORTED = "unsupported"


class GeneralResearchRequest(DomainModel):
    """A broad FPL research question with optional manager state."""

    schema_version: Literal["1.0"] = "1.0"
    squad: CurrentSquadInput | None = None
    selling_prices_tenths: dict[int, int] = Field(default_factory=dict)
    risk_preference: RiskPreference = RiskPreference.BALANCED
    horizon_gameweeks: int | None = Field(default=None, ge=1, le=2)
    maximum_points_hit: int | None = Field(default=None, ge=0, multiple_of=4)
    protected_player_ids: tuple[int, ...] = ()
    question: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def state_references_are_valid(self) -> "GeneralResearchRequest":
        squad_ids = set(self.squad.player_ids) if self.squad is not None else set()
        if self.squad is None and self.selling_prices_tenths:
            raise ValueError("selling prices require a confirmed squad")
        if not set(self.selling_prices_tenths).issubset(squad_ids):
            raise ValueError("selling prices may only reference players in the confirmed squad")
        if any(price < 0 or price > 300 for price in self.selling_prices_tenths.values()):
            raise ValueError("every selling price must be between £0.0m and £30.0m")
        if len(set(self.protected_player_ids)) != len(self.protected_player_ids):
            raise ValueError("protected players must be unique")
        if not set(self.protected_player_ids).issubset(squad_ids):
            raise ValueError("protected players must belong to the confirmed squad")
        return self


class ResearchFact(DomainModel):
    """One labelled fact or calculation shown in a general research report."""

    subject: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    nature: EvidenceNature
    source: str = Field(min_length=1)


class ResearchCalculation(DomainModel):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    formula: str = Field(min_length=1)


class ResearchAlternative(DomainModel):
    rank: int = Field(ge=1, le=2)
    player: Player | None = None
    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    facts: tuple[ResearchFact, ...] = ()


class GeneralResearchReport(DomainModel):
    """Common, inspectable answer envelope for every Slice 4 capability."""

    schema_version: Literal["1.0"] = "1.0"
    question: str = Field(min_length=1)
    capability: ResearchCapability
    status: GeneralResearchStatus
    subject: Player | None = None
    recommended_action: str = Field(min_length=1)
    alternatives: tuple[ResearchAlternative, ...] = Field(default=(), max_length=2)
    facts: tuple[ResearchFact, ...] = Field(min_length=1)
    calculations: tuple[ResearchCalculation, ...] = ()
    opinion: str = Field(min_length=1)
    strongest_objection: str = Field(min_length=1)
    change_conditions: tuple[str, ...] = Field(min_length=1)
    clarification_question: str | None = None
    grounded_reasons: tuple[GroundedReason, ...] = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    evidence: PlayerEvidenceReport | None = None
    named_target_report: NamedTargetResearchReport | None = None
    route_report: MultiGameweekRouteReport | None = None
    squad_action_report: SquadActionReport | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def clarification_matches_status(self) -> "GeneralResearchReport":
        is_clarification = self.status is GeneralResearchStatus.NEEDS_CLARIFICATION
        if is_clarification != (self.clarification_question is not None):
            raise ValueError("clarification reports must contain exactly one question")
        return self


class GeneralResearchResponse(DomainModel):
    report: GeneralResearchReport
    assistant_message: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class GeneralSynthesisSelection(DomainModel):
    status: GeneralResearchStatus
    reason_ids: tuple[str, ...] = Field(min_length=1, max_length=4)
