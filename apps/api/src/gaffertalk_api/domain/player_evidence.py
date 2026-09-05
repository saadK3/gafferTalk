from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from gaffertalk_api.domain.models import Club, DomainModel, Money, Position


class EvidenceAvailability(StrEnum):
    OBSERVED = "observed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class EvidenceFreshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"


class EvidenceNature(StrEnum):
    OBSERVED = "observed"
    MODEL_DERIVED = "model_derived"
    CALCULATED = "calculated"


class EvidenceSource(DomainModel):
    provider: Literal["official_fpl"] = "official_fpl"
    endpoint: str = Field(min_length=1)
    fetched_at: datetime
    published_at: datetime | None = None


class PlayerEvidenceRequest(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    player_ids: tuple[int, ...] = Field(min_length=1)
    recent_gameweeks: int = Field(default=5, ge=1, le=10)
    stale_after_minutes: int = Field(default=60, ge=1, le=1440)

    @model_validator(mode="after")
    def player_ids_are_unique(self) -> "PlayerEvidenceRequest":
        if len(set(self.player_ids)) != len(self.player_ids):
            raise ValueError("player IDs must be unique")
        if any(player_id <= 0 for player_id in self.player_ids):
            raise ValueError("player IDs must be positive")
        return self


class CurrentFplEvidence(DomainModel):
    price: Money | None
    status: str | None
    chance_of_playing_next_round: int | None = Field(default=None, ge=0, le=100)
    news: str | None
    news_published_at: datetime | None
    source: EvidenceSource


class SeasonTotalsEvidence(DomainModel):
    points: int | None
    minutes: int | None = Field(default=None, ge=0)
    starts: int | None = Field(default=None, ge=0)
    goals: int | None = Field(default=None, ge=0)
    assists: int | None = Field(default=None, ge=0)
    bonus: int | None = Field(default=None, ge=0)
    expected_goals: float | None = Field(default=None, ge=0)
    expected_assists: float | None = Field(default=None, ge=0)
    expected_metrics_nature: Literal[EvidenceNature.MODEL_DERIVED] = EvidenceNature.MODEL_DERIVED
    source: EvidenceSource


class MatchEvidence(DomainModel):
    fixture_id: int | None = Field(default=None, gt=0)
    opponent_club_id: int | None = Field(default=None, gt=0)
    was_home: bool | None = None
    kickoff_time: datetime | None = None
    points: int | None
    minutes: int | None = Field(default=None, ge=0)
    starts: int | None = Field(default=None, ge=0)
    expected_goals: float | None = Field(default=None, ge=0)
    expected_assists: float | None = Field(default=None, ge=0)
    source: EvidenceSource


class GameweekHistoryEvidence(DomainModel):
    gameweek_id: int = Field(ge=1, le=38)
    matches: tuple[MatchEvidence, ...] = Field(min_length=1)
    total_points: int | None
    total_minutes: int | None = Field(default=None, ge=0)
    total_starts: int | None = Field(default=None, ge=0)


class HistoricalExpectedInvolvement(DomainModel):
    expected_goals: float | None = Field(default=None, ge=0)
    expected_assists: float | None = Field(default=None, ge=0)
    minutes_denominator: int | None = Field(default=None, ge=0)
    gameweek_ids: tuple[int, ...]
    match_count: int = Field(ge=0)
    nature: Literal[EvidenceNature.MODEL_DERIVED] = EvidenceNature.MODEL_DERIVED
    source: EvidenceSource


class RecentHistoryEvidence(DomainModel):
    requested_gameweeks: int = Field(ge=1, le=10)
    included_gameweek_ids: tuple[int, ...]
    match_count: int = Field(ge=0)
    gameweeks: tuple[GameweekHistoryEvidence, ...]
    expected_involvement: HistoricalExpectedInvolvement
    source: EvidenceSource


class ScheduledFixtureEvidence(DomainModel):
    fixture_id: int = Field(gt=0)
    gameweek_id: int | None = Field(default=None, ge=1, le=38)
    kickoff_time: datetime | None
    opponent_club_id: int = Field(gt=0)
    is_home: bool
    difficulty: int = Field(ge=1, le=5)
    sources: tuple[EvidenceSource, ...] = Field(min_length=1)


class EvidenceConflict(DomainModel):
    code: str = Field(pattern=r"^[a-z0-9_]+$")
    message: str = Field(min_length=1)
    source_endpoints: tuple[str, ...] = Field(min_length=2)


class PlayerEvidence(DomainModel):
    player_id: int = Field(gt=0)
    web_name: str = Field(min_length=1)
    club: Club
    position: Position
    availability: EvidenceAvailability
    current: CurrentFplEvidence
    season_totals: SeasonTotalsEvidence
    recent_history: RecentHistoryEvidence | None
    upcoming_fixtures: tuple[ScheduledFixtureEvidence, ...]
    missing_fields: tuple[str, ...]
    conflicts: tuple[EvidenceConflict, ...]


class PlayerEvidenceReport(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    freshness: EvidenceFreshness
    players: tuple[PlayerEvidence, ...] = Field(min_length=1)
    sources: tuple[EvidenceSource, ...] = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
