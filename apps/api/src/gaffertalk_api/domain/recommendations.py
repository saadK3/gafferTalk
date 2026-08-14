from enum import StrEnum

from pydantic import Field, model_validator

from gaffertalk_api.domain.models import DomainModel, Money, Player


class RecommendationStrategy(StrEnum):
    BALANCED = "balanced"
    FIXTURE_FIRST = "fixture_first"
    VALUE_FIRST = "value_first"


class ScoreWeights(DomainModel):
    historical_output: float = Field(ge=0, le=1)
    upcoming_fixtures: float = Field(ge=0, le=1)
    value: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def total_one(self) -> "ScoreWeights":
        if abs(self.historical_output + self.upcoming_fixtures + self.value - 1) > 0.0001:
            raise ValueError("recommendation score weights must total 1")
        return self


STRATEGY_WEIGHTS = {
    RecommendationStrategy.BALANCED: ScoreWeights(
        historical_output=0.45,
        upcoming_fixtures=0.35,
        value=0.20,
    ),
    RecommendationStrategy.FIXTURE_FIRST: ScoreWeights(
        historical_output=0.25,
        upcoming_fixtures=0.60,
        value=0.15,
    ),
    RecommendationStrategy.VALUE_FIRST: ScoreWeights(
        historical_output=0.25,
        upcoming_fixtures=0.20,
        value=0.55,
    ),
}


class ScoreBreakdown(DomainModel):
    historical_output: float = Field(ge=0, le=100)
    upcoming_fixtures: float = Field(ge=0, le=100)
    value: float = Field(ge=0, le=100)


class TransferRecommendation(DomainModel):
    rank: int = Field(gt=0)
    outgoing: Player
    incoming: Player
    score: float = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown
    average_fixture_difficulty: float | None = Field(default=None, ge=1, le=5)
    fixtures_considered: int = Field(ge=0)
    remaining_bank: Money
    free_transfers_after: int = Field(ge=0, le=5)
    points_hit: int = Field(ge=0)
    reasons: tuple[str, ...]
    trade_off: str


class RecommendationResult(DomainModel):
    squad_name: str
    outgoing: Player
    strategy: RecommendationStrategy
    score_weights: ScoreWeights
    recommendations: tuple[TransferRecommendation, ...]
    assumptions: tuple[str, ...]
