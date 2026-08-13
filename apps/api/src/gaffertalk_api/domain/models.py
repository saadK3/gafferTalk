from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DomainModel(BaseModel):
    """Immutable base for data that has crossed the upstream adapter boundary."""

    model_config = ConfigDict(frozen=True)


class DataProvenance(StrEnum):
    OBSERVED = "observed"
    DERIVED = "derived"
    USER_SUPPLIED = "user_supplied"
    UNAVAILABLE = "unavailable"


class Position(StrEnum):
    GOALKEEPER = "GKP"
    DEFENDER = "DEF"
    MIDFIELDER = "MID"
    FORWARD = "FWD"


class SquadAvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    NOT_YET_PUBLISHED = "not_yet_published"


class Money(DomainModel):
    """FPL monetary value in integer tenths of a million pounds."""

    tenths: int = Field(ge=0)


class Club(DomainModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    short_name: str = Field(min_length=1)


class Gameweek(DomainModel):
    id: int = Field(ge=1, le=38)
    name: str = Field(min_length=1)
    deadline_time: datetime
    finished: bool
    data_checked: bool
    is_previous: bool
    is_current: bool
    is_next: bool


class Player(DomainModel):
    id: int = Field(gt=0)
    web_name: str = Field(min_length=1)
    club: Club
    position: Position
    current_price: Money
    status: str = Field(min_length=1)
    chance_of_playing_next_round: int | None = Field(default=None, ge=0, le=100)
    news: str = ""
    total_points: int = 0
    minutes: int = Field(default=0, ge=0)
    starts: int = Field(default=0, ge=0)
    expected_goals: float = Field(default=0, ge=0)
    expected_assists: float = Field(default=0, ge=0)
    selected_by_percent: float = Field(default=0, ge=0, le=100)


class Fixture(DomainModel):
    id: int = Field(gt=0)
    gameweek_id: int | None = Field(default=None, ge=1, le=38)
    kickoff_time: datetime | None
    home_club_id: int = Field(gt=0)
    away_club_id: int = Field(gt=0)
    home_difficulty: int = Field(ge=1, le=5)
    away_difficulty: int = Field(ge=1, le=5)
    started: bool
    finished: bool


class GameRules(DomainModel):
    squad_size: int = Field(gt=0)
    starting_size: int = Field(gt=0)
    club_limit: int = Field(gt=0)
    initial_budget: Money
    currency_multiplier: int = Field(gt=0)
    maximum_extra_free_transfers: int = Field(ge=0)
    squad_size_by_position: dict[Position, int]
    minimum_starting_by_position: dict[Position, int]


class FplCatalogue(DomainModel):
    players: dict[int, Player]
    clubs: dict[int, Club]
    gameweeks: tuple[Gameweek, ...]
    rules: GameRules
    retrieved_at: datetime


class EntrySummary(DomainModel):
    id: int = Field(gt=0)
    team_name: str = Field(min_length=1)
    manager_first_name: str | None = None
    manager_last_name: str | None = None
    current_gameweek_id: int | None = Field(default=None, ge=1, le=38)
    started_gameweek_id: int = Field(ge=1, le=38)
    overall_points: int | None = Field(default=None, ge=0)
    overall_rank: int | None = Field(default=None, ge=1)
    last_deadline_bank: Money | None = None
    last_deadline_value: Money | None = None
    financial_provenance: DataProvenance


class SquadPick(DomainModel):
    player: Player
    squad_position: int = Field(ge=1, le=15)
    multiplier: int = Field(ge=0, le=3)
    is_captain: bool
    is_vice_captain: bool


class SquadSnapshot(DomainModel):
    gameweek: Gameweek
    picks: tuple[SquadPick, ...]
    bank: Money | None
    squad_value: Money | None
    event_transfers: int | None = Field(default=None, ge=0)
    event_transfer_cost: int | None = Field(default=None, ge=0)
    active_chip: str | None = None
    provenance: DataProvenance = DataProvenance.OBSERVED
    retrieved_at: datetime

    @model_validator(mode="after")
    def validate_squad(self) -> "SquadSnapshot":
        if len(self.picks) != 15:
            raise ValueError("a finalized FPL squad must contain exactly 15 picks")
        if len({pick.squad_position for pick in self.picks}) != 15:
            raise ValueError("squad positions must be unique")
        if sum(pick.is_captain for pick in self.picks) != 1:
            raise ValueError("a finalized squad must contain exactly one captain")
        if sum(pick.is_vice_captain for pick in self.picks) != 1:
            raise ValueError("a finalized squad must contain exactly one vice-captain")
        if any(pick.is_captain and pick.is_vice_captain for pick in self.picks):
            raise ValueError("captain and vice-captain must be different players")

        expected_positions = {
            Position.GOALKEEPER: 2,
            Position.DEFENDER: 5,
            Position.MIDFIELDER: 5,
            Position.FORWARD: 3,
        }
        actual_positions = {
            position: sum(pick.player.position is position for pick in self.picks)
            for position in Position
        }
        if actual_positions != expected_positions:
            raise ValueError("squad must contain 2 GKP, 5 DEF, 5 MID, and 3 FWD")

        club_counts = {
            club_id: sum(pick.player.club.id == club_id for pick in self.picks)
            for club_id in {pick.player.club.id for pick in self.picks}
        }
        if any(count > 3 for count in club_counts.values()):
            raise ValueError("squad cannot contain more than three players from one club")
        return self


class SquadAvailability(DomainModel):
    status: SquadAvailabilityStatus
    reason: str
    next_deadline: datetime | None = None


class SquadLookupResult(DomainModel):
    entry: EntrySummary
    availability: SquadAvailability
    snapshot: SquadSnapshot | None
    retrieved_at: datetime

    @model_validator(mode="after")
    def validate_availability(self) -> "SquadLookupResult":
        has_snapshot = self.snapshot is not None
        is_available = self.availability.status is SquadAvailabilityStatus.AVAILABLE
        if has_snapshot != is_available:
            raise ValueError("availability and snapshot must agree")
        return self
