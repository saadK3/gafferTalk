from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FplSchema(BaseModel):
    """Base model that tolerates additive upstream fields but validates known ones."""

    model_config = ConfigDict(extra="ignore")


class FplEvent(FplSchema):
    id: int = Field(ge=1, le=38)
    name: str = Field(min_length=1)
    deadline_time: datetime
    finished: bool = False
    data_checked: bool = False
    is_previous: bool = False
    is_current: bool = False
    is_next: bool = False


class FplTeam(FplSchema):
    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    short_name: str = Field(min_length=1)


class FplElementType(FplSchema):
    id: int = Field(gt=0)
    singular_name_short: str = Field(min_length=1)
    squad_select: int = Field(gt=0)
    squad_min_play: int = Field(ge=0)
    squad_max_play: int = Field(ge=0)


class FplElement(FplSchema):
    id: int = Field(gt=0)
    web_name: str = Field(min_length=1)
    first_name: str = ""
    second_name: str = ""
    team: int = Field(gt=0)
    element_type: int = Field(gt=0)
    now_cost: int = Field(ge=0)
    status: str = Field(min_length=1)
    chance_of_playing_next_round: int | None = Field(default=None, ge=0, le=100)
    news: str = ""
    total_points: int = 0
    minutes: int = Field(default=0, ge=0)
    starts: int = Field(default=0, ge=0)
    expected_goals: float = Field(default=0, ge=0)
    expected_assists: float = Field(default=0, ge=0)
    selected_by_percent: float = Field(default=0, ge=0, le=100)


class FplGameSettings(FplSchema):
    squad_squadplay: int = Field(gt=0)
    squad_squadsize: int = Field(gt=0)
    squad_team_limit: int = Field(gt=0)
    squad_total_spend: int = Field(gt=0)
    ui_currency_multiplier: int = Field(gt=0)
    max_extra_free_transfers: int = Field(ge=0)


class FplBootstrap(FplSchema):
    events: list[FplEvent]
    teams: list[FplTeam]
    elements: list[FplElement]
    element_types: list[FplElementType]
    game_settings: FplGameSettings


class FplFixture(FplSchema):
    id: int = Field(gt=0)
    event: int | None = Field(default=None, ge=1, le=38)
    kickoff_time: datetime | None = None
    team_h: int = Field(gt=0)
    team_a: int = Field(gt=0)
    team_h_difficulty: int = Field(ge=1, le=5)
    team_a_difficulty: int = Field(ge=1, le=5)
    started: bool = False
    finished: bool = False


class FplEntry(FplSchema):
    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    player_first_name: str | None = None
    player_last_name: str | None = None
    current_event: int | None = Field(default=None, ge=1, le=38)
    started_event: int = Field(ge=1, le=38)
    summary_overall_points: int | None = Field(default=None, ge=0)
    summary_overall_rank: int | None = Field(default=None, ge=1)
    last_deadline_bank: int | None = Field(default=None, ge=0)
    last_deadline_value: int | None = Field(default=None, ge=0)
    last_deadline_total_transfers: int = Field(default=0, ge=0)


class FplEntryHistoryEvent(FplSchema):
    event: int = Field(ge=1, le=38)
    points: int
    total_points: int = Field(ge=0)
    rank: int | None = Field(default=None, ge=1)
    overall_rank: int | None = Field(default=None, ge=1)
    bank: int = Field(ge=0)
    value: int = Field(ge=0)
    event_transfers: int = Field(ge=0)
    event_transfers_cost: int = Field(ge=0)
    points_on_bench: int


class FplEntryHistory(FplSchema):
    current: list[FplEntryHistoryEvent]
    past: list[dict[str, Any]]
    chips: list[dict[str, Any]]


class FplTransfer(FplSchema):
    element_in: int = Field(gt=0)
    element_in_cost: int = Field(ge=0)
    element_out: int = Field(gt=0)
    element_out_cost: int = Field(ge=0)
    entry: int = Field(gt=0)
    event: int = Field(ge=1, le=38)
    time: datetime


class FplPick(FplSchema):
    element: int = Field(gt=0)
    position: int = Field(ge=1, le=15)
    multiplier: int = Field(ge=0, le=3)
    is_captain: bool
    is_vice_captain: bool


class FplPicks(FplSchema):
    active_chip: str | None = None
    automatic_subs: list[dict[str, Any]] = Field(default_factory=list)
    entry_history: FplEntryHistoryEvent
    picks: list[FplPick]


class FplElementSummary(FplSchema):
    fixtures: list[dict[str, Any]]
    history: list[dict[str, Any]]
    history_past: list[dict[str, Any]]
