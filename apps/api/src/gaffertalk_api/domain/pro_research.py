from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from gaffertalk_api.domain.models import DataProvenance, DomainModel, Money, Player


class ProVerdict(StrEnum):
    BUY = "buy"
    HOLD = "hold"
    WAIT = "wait"
    AVOID = "avoid"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DecisionAction(StrEnum):
    REQUESTED_TRANSFER = "requested_transfer"
    HOLD = "hold"
    WAIT = "wait"
    ALTERNATIVE_TRANSFER = "alternative_transfer"


class EvidenceMetric(DomainModel):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: float
    display_value: str = Field(min_length=1)
    provenance: DataProvenance
    source: str = Field(min_length=1)


class FixtureRun(DomainModel):
    difficulties: tuple[int, ...] = Field(max_length=5)
    average_difficulty: float | None = Field(default=None, ge=1, le=5)
    fixtures_considered: int = Field(ge=0, le=5)


class PlayerEvidence(DomainModel):
    player: Player
    metrics: tuple[EvidenceMetric, ...]
    next_five: FixtureRun
    next_three: FixtureRun
    recent_gameweeks: tuple[int, ...] = Field(max_length=5)
    evidence_score: float = Field(ge=0, le=100)
    source_retrieved_at: datetime


class LegalTransferRoute(DomainModel):
    outgoing: Player
    incoming: Player
    remaining_bank: Money
    free_transfers_after: int = Field(ge=0, le=5)
    points_hit: int = Field(ge=0)


class DecisionAlternative(DomainModel):
    action: DecisionAction
    player: Player | None = None
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def transfer_has_player(self) -> "DecisionAlternative":
        is_transfer = self.action in {
            DecisionAction.REQUESTED_TRANSFER,
            DecisionAction.ALTERNATIVE_TRANSFER,
        }
        if is_transfer != (self.player is not None):
            raise ValueError("transfer alternatives must include a player")
        return self


class SquadPriority(DomainModel):
    more_urgent: bool
    player: Player | None = None
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def urgent_priority_has_player(self) -> "SquadPriority":
        if self.more_urgent != (self.player is not None):
            raise ValueError("an urgent squad priority must identify a player")
        return self


class OpportunityCost(DomainModel):
    free_transfers_used: int = Field(ge=0, le=2)
    points_hit: int = Field(ge=0)
    remaining_bank: Money
    flexibility: Literal["strong", "moderate", "limited"]
    explanation: str = Field(min_length=1)


class DecisionConfidence(DomainModel):
    level: ConfidenceLevel
    policy_version: Literal["1.0"] = "1.0"
    reasons: tuple[str, ...] = Field(min_length=1)


class GroundedReason(DomainModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    text: str = Field(min_length=1)


class ProDecisionReport(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    squad_name: str = Field(min_length=1)
    created_at: datetime
    data_retrieved_at: datetime
    verdict: ProVerdict
    recommended_action: str = Field(min_length=1)
    compared_actions: tuple[DecisionAction, ...] = Field(min_length=3)
    requested_route: LegalTransferRoute
    case_for: tuple[str, ...] = Field(min_length=1)
    case_against: tuple[str, ...] = Field(min_length=1)
    best_alternative: DecisionAlternative
    squad_priority: SquadPriority
    opportunity_cost: OpportunityCost
    planning_impact: str = Field(min_length=1)
    confidence: DecisionConfidence
    change_conditions: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[PlayerEvidence, ...] = Field(min_length=2)
    assumptions: tuple[str, ...] = Field(min_length=1)
    grounded_reasons: tuple[GroundedReason, ...] = Field(min_length=1)


class NamedTransferResearchResponse(DomainModel):
    report: ProDecisionReport
    assistant_message: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class ProSynthesisSelection(DomainModel):
    verdict: ProVerdict
    reason_ids: tuple[str, ...] = Field(min_length=1, max_length=3)


class RiskPreference(StrEnum):
    SAFE = "safe"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class SquadActionKind(StrEnum):
    TRANSFER = "transfer"
    ROLL = "roll"


class SquadActionStatus(StrEnum):
    NEEDS_SELLING_PRICE = "needs_selling_price"
    TRANSFER = "transfer"
    ROLL = "roll"
    INSUFFICIENT_GAIN = "insufficient_gain"


class ConcernKind(StrEnum):
    AVAILABILITY = "availability"
    MINUTES = "minutes"
    UPGRADE = "upgrade"
    BENCH_RELIANCE = "bench_reliance"


class RankedSquadConcern(DomainModel):
    rank: int = Field(ge=1, le=15)
    player: Player
    kind: ConcernKind
    priority_score: float = Field(ge=0, le=100)
    starting_slot: bool
    explanation: str = Field(min_length=1)


class SquadActionCandidate(DomainModel):
    action: SquadActionKind
    outgoing: Player | None = None
    incoming: Player | None = None
    evidence_gain: float
    policy_adjusted_gain: float
    remaining_bank: Money
    free_transfers_used: int = Field(ge=0, le=1)
    free_transfers_after: int = Field(ge=0, le=5)
    points_hit: int = Field(ge=0)
    budget_status: Literal["optimistic", "exact", "not_applicable"]
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def transfer_has_players(self) -> "SquadActionCandidate":
        has_route = self.outgoing is not None and self.incoming is not None
        if (self.action is SquadActionKind.TRANSFER) != has_route:
            raise ValueError("a transfer action must include outgoing and incoming players")
        return self


class HitAnalysis(DomainModel):
    points_hit: int = Field(ge=0)
    justified: bool
    transfer_adjusted_gain: float
    required_gain: float = Field(ge=0)
    comparison: str = Field(min_length=1)


class SquadActionConfidence(DomainModel):
    level: ConfidenceLevel
    policy_version: Literal["1.0"] = "1.0"
    reasons: tuple[str, ...] = Field(min_length=1)


class SquadActionReport(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    decision_policy_version: Literal["1.0"] = "1.0"
    squad_name: str = Field(min_length=1)
    created_at: datetime
    data_retrieved_at: datetime
    risk_preference: RiskPreference
    status: SquadActionStatus
    recommended_action: SquadActionCandidate | None = None
    provisional_action: SquadActionCandidate | None = None
    requested_selling_price_for: Player | None = None
    ranked_concerns: tuple[RankedSquadConcern, ...] = Field(min_length=1, max_length=15)
    compared_actions: tuple[SquadActionCandidate, ...] = Field(min_length=2)
    roll_threshold: float = Field(ge=0)
    priority_explanation: str = Field(min_length=1)
    hit_analysis: HitAnalysis
    planning_impact: str = Field(min_length=1)
    confidence: SquadActionConfidence
    change_conditions: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[PlayerEvidence, ...] = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    grounded_reasons: tuple[GroundedReason, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def status_matches_actions(self) -> "SquadActionReport":
        needs_price = self.status is SquadActionStatus.NEEDS_SELLING_PRICE
        if needs_price:
            if (
                self.recommended_action is not None
                or self.provisional_action is None
                or self.requested_selling_price_for is None
            ):
                raise ValueError("a preliminary report must request one selling price")
        elif self.recommended_action is None:
            raise ValueError("a final report must include a recommended action")
        if self.status is SquadActionStatus.TRANSFER and (
            self.recommended_action is None
            or self.recommended_action.action is not SquadActionKind.TRANSFER
            or self.recommended_action.budget_status != "exact"
        ):
            raise ValueError("a final transfer must be exact")
        if self.status in {SquadActionStatus.ROLL, SquadActionStatus.INSUFFICIENT_GAIN} and (
            self.recommended_action is None
            or self.recommended_action.action is not SquadActionKind.ROLL
        ):
            raise ValueError("a roll outcome must recommend rolling")
        return self


class SquadActionResearchResponse(DomainModel):
    report: SquadActionReport
    assistant_message: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class SquadActionSynthesisSelection(DomainModel):
    status: SquadActionStatus
    reason_ids: tuple[str, ...] = Field(min_length=1, max_length=3)
