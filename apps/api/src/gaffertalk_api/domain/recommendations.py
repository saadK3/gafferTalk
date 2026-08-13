from pydantic import Field

from gaffertalk_api.domain.models import DomainModel, Money, Player


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
    reasons: tuple[str, ...]
    trade_off: str


class RecommendationResult(DomainModel):
    synthetic_squad_name: str
    outgoing: Player
    recommendations: tuple[TransferRecommendation, ...]
    assumptions: tuple[str, ...]
