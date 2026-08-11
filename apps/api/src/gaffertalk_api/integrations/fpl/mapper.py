from datetime import datetime

from gaffertalk_api.domain.errors import InvalidUpstreamFplResponseError
from gaffertalk_api.domain.models import (
    Club,
    DataProvenance,
    EntrySummary,
    Fixture,
    FplCatalogue,
    GameRules,
    Gameweek,
    Money,
    Player,
    Position,
    SquadPick,
    SquadSnapshot,
)
from gaffertalk_api.integrations.fpl.schemas import (
    FplBootstrap,
    FplEntry,
    FplFixture,
    FplPicks,
)

POSITION_BY_SHORT_NAME = {
    "GKP": Position.GOALKEEPER,
    "DEF": Position.DEFENDER,
    "MID": Position.MIDFIELDER,
    "FWD": Position.FORWARD,
}


def map_catalogue(bootstrap: FplBootstrap, retrieved_at: datetime) -> FplCatalogue:
    clubs = {
        team.id: Club(id=team.id, name=team.name, short_name=team.short_name)
        for team in bootstrap.teams
    }
    positions: dict[int, Position] = {}
    for element_type in bootstrap.element_types:
        position = POSITION_BY_SHORT_NAME.get(element_type.singular_name_short)
        if position is None:
            raise InvalidUpstreamFplResponseError(
                f"unknown FPL position {element_type.singular_name_short!r}"
            )
        positions[element_type.id] = position

    players: dict[int, Player] = {}
    for element in bootstrap.elements:
        club = clubs.get(element.team)
        position = positions.get(element.element_type)
        if club is None or position is None:
            raise InvalidUpstreamFplResponseError(
                f"player {element.id} references an unknown club or position"
            )
        players[element.id] = Player(
            id=element.id,
            web_name=element.web_name,
            club=club,
            position=position,
            current_price=Money(tenths=element.now_cost),
            status=element.status,
            chance_of_playing_next_round=element.chance_of_playing_next_round,
            news=element.news,
        )

    gameweeks = tuple(
        Gameweek(
            id=event.id,
            name=event.name,
            deadline_time=event.deadline_time,
            finished=event.finished,
            data_checked=event.data_checked,
            is_previous=event.is_previous,
            is_current=event.is_current,
            is_next=event.is_next,
        )
        for event in sorted(bootstrap.events, key=lambda item: item.id)
    )
    settings = bootstrap.game_settings
    return FplCatalogue(
        players=players,
        clubs=clubs,
        gameweeks=gameweeks,
        rules=GameRules(
            squad_size=settings.squad_squadsize,
            starting_size=settings.squad_squadplay,
            club_limit=settings.squad_team_limit,
            initial_budget=Money(tenths=settings.squad_total_spend),
            currency_multiplier=settings.ui_currency_multiplier,
            maximum_extra_free_transfers=settings.max_extra_free_transfers,
        ),
        retrieved_at=retrieved_at,
    )


def map_fixtures(fixtures: tuple[FplFixture, ...]) -> tuple[Fixture, ...]:
    return tuple(
        Fixture(
            id=fixture.id,
            gameweek_id=fixture.event,
            kickoff_time=fixture.kickoff_time,
            home_club_id=fixture.team_h,
            away_club_id=fixture.team_a,
            home_difficulty=fixture.team_h_difficulty,
            away_difficulty=fixture.team_a_difficulty,
            started=fixture.started,
            finished=fixture.finished,
        )
        for fixture in fixtures
    )


def map_entry(entry: FplEntry) -> EntrySummary:
    has_financial_snapshot = (
        entry.last_deadline_bank is not None and entry.last_deadline_value is not None
    )
    return EntrySummary(
        id=entry.id,
        team_name=entry.name,
        manager_first_name=entry.player_first_name,
        manager_last_name=entry.player_last_name,
        current_gameweek_id=entry.current_event,
        started_gameweek_id=entry.started_event,
        overall_points=entry.summary_overall_points,
        overall_rank=entry.summary_overall_rank,
        last_deadline_bank=(
            Money(tenths=entry.last_deadline_bank) if entry.last_deadline_bank is not None else None
        ),
        last_deadline_value=(
            Money(tenths=entry.last_deadline_value)
            if entry.last_deadline_value is not None
            else None
        ),
        financial_provenance=(
            DataProvenance.OBSERVED if has_financial_snapshot else DataProvenance.UNAVAILABLE
        ),
    )


def map_squad_snapshot(
    picks: FplPicks,
    gameweek: Gameweek,
    catalogue: FplCatalogue,
    retrieved_at: datetime,
) -> SquadSnapshot:
    mapped_picks: list[SquadPick] = []
    for pick in sorted(picks.picks, key=lambda item: item.position):
        player = catalogue.players.get(pick.element)
        if player is None:
            raise InvalidUpstreamFplResponseError(f"squad references unknown player {pick.element}")
        mapped_picks.append(
            SquadPick(
                player=player,
                squad_position=pick.position,
                multiplier=pick.multiplier,
                is_captain=pick.is_captain,
                is_vice_captain=pick.is_vice_captain,
            )
        )

    history = picks.entry_history
    return SquadSnapshot(
        gameweek=gameweek,
        picks=tuple(mapped_picks),
        bank=Money(tenths=history.bank),
        squad_value=Money(tenths=history.value),
        event_transfers=history.event_transfers,
        event_transfer_cost=history.event_transfers_cost,
        active_chip=picks.active_chip,
        retrieved_at=retrieved_at,
    )
