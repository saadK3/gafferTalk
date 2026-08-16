from datetime import UTC, datetime

from gaffertalk_api.domain.models import (
    Club,
    DataProvenance,
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
from gaffertalk_api.domain.recommendations import RecommendationStrategy
from gaffertalk_api.domain.transfers import TransferPlanningState
from gaffertalk_api.services.one_player_recommendations import OnePlayerRecommendationService

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def player(
    player_id: int,
    position: Position,
    club: Club,
    *,
    price: int = 50,
    points: int = 100,
    status: str = "a",
) -> Player:
    return Player(
        id=player_id,
        web_name=f"Player {player_id}",
        club=club,
        position=position,
        current_price=Money(tenths=price),
        status=status,
        total_points=points,
    )


def test_recommendations_are_ranked_and_illegal_candidates_are_removed() -> None:
    clubs = {
        club_id: Club(id=club_id, name=f"Club {club_id}", short_name=f"C{club_id}")
        for club_id in range(1, 16)
    }
    positions = (
        [Position.GOALKEEPER] * 2
        + [Position.DEFENDER] * 5
        + [Position.MIDFIELDER] * 5
        + [Position.FORWARD] * 3
    )
    squad_players = [
        player(index, position, clubs[1 if index <= 3 else index - 1])
        for index, position in enumerate(positions, start=1)
    ]
    outgoing = squad_players[7]
    better = player(101, Position.MIDFIELDER, clubs[15], price=55, points=180)
    cheaper = player(102, Position.MIDFIELDER, clubs[14], price=45, points=130)
    fourth_from_club = player(103, Position.MIDFIELDER, clubs[1], price=45, points=999)
    unavailable = player(104, Position.MIDFIELDER, clubs[13], price=45, points=999, status="i")
    unaffordable = player(105, Position.MIDFIELDER, clubs[12], price=70, points=999)
    all_players = squad_players + [
        better,
        cheaper,
        fourth_from_club,
        unavailable,
        unaffordable,
    ]
    gameweek = Gameweek(
        id=1,
        name="Gameweek 1",
        deadline_time=NOW,
        finished=False,
        data_checked=False,
        is_previous=False,
        is_current=False,
        is_next=True,
    )
    catalogue = FplCatalogue(
        players={item.id: item for item in all_players},
        clubs=clubs,
        gameweeks=(gameweek,),
        rules=GameRules(
            squad_size=15,
            starting_size=11,
            club_limit=3,
            initial_budget=Money(tenths=1000),
            currency_multiplier=10,
            maximum_extra_free_transfers=4,
            squad_size_by_position={
                Position.GOALKEEPER: 2,
                Position.DEFENDER: 5,
                Position.MIDFIELDER: 5,
                Position.FORWARD: 3,
            },
            minimum_starting_by_position={
                Position.GOALKEEPER: 1,
                Position.DEFENDER: 3,
                Position.MIDFIELDER: 2,
                Position.FORWARD: 1,
            },
        ),
        retrieved_at=NOW,
    )
    snapshot = SquadSnapshot(
        gameweek=gameweek,
        picks=tuple(
            SquadPick(
                player=item,
                squad_position=index,
                multiplier=2 if index == 1 else 1 if index <= 11 else 0,
                is_captain=index == 1,
                is_vice_captain=index == 2,
            )
            for index, item in enumerate(squad_players, start=1)
        ),
        bank=Money(tenths=5),
        squad_value=Money(tenths=750),
        provenance=DataProvenance.DERIVED,
        retrieved_at=NOW,
    )
    fixtures = tuple(
        Fixture(
            id=index,
            gameweek_id=index,
            kickoff_time=None,
            home_club_id=15,
            away_club_id=14,
            home_difficulty=2,
            away_difficulty=4,
            started=False,
            finished=False,
        )
        for index in range(1, 6)
    )
    state = TransferPlanningState(
        bank=Money(tenths=5),
        free_transfers=1,
        selling_prices={outgoing.id: outgoing.current_price},
    )

    result = OnePlayerRecommendationService().recommend(
        squad_name="Test squad",
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        outgoing_player_id=outgoing.id,
    )

    assert [item.incoming.id for item in result.recommendations] == [better.id, cheaper.id]
    assert result.recommendations[0].remaining_bank == Money(tenths=0)
    assert result.recommendations[0].free_transfers_after == 0
    assert result.recommendations[0].points_hit == 0
    assert all(item.incoming.position is outgoing.position for item in result.recommendations)
    assert "loaded live from FPL" in result.assumptions[0]

    targeted = OnePlayerRecommendationService().recommend(
        squad_name="Test squad",
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        outgoing_player_id=outgoing.id,
        target_player_id=cheaper.id,
    )
    assert [item.incoming.id for item in targeted.recommendations] == [cheaper.id]


def test_quick_actions_use_distinct_weights_and_change_ranking() -> None:
    clubs = {
        club_id: Club(id=club_id, name=f"Club {club_id}", short_name=f"C{club_id}")
        for club_id in range(1, 18)
    }
    positions = (
        [Position.GOALKEEPER] * 2
        + [Position.DEFENDER] * 5
        + [Position.MIDFIELDER] * 5
        + [Position.FORWARD] * 3
    )
    squad_players = [
        player(index, position, clubs[index]) for index, position in enumerate(positions, start=1)
    ]
    outgoing = squad_players[7]
    output_pick = player(101, Position.MIDFIELDER, clubs[16], price=60, points=200)
    fixture_pick = player(102, Position.MIDFIELDER, clubs[17], price=55, points=120)
    value_pick = player(103, Position.MIDFIELDER, clubs[15], price=40, points=150)
    gameweek = Gameweek(
        id=1,
        name="Gameweek 1",
        deadline_time=NOW,
        finished=False,
        data_checked=False,
        is_previous=False,
        is_current=False,
        is_next=True,
    )
    catalogue = FplCatalogue(
        players={item.id: item for item in squad_players + [output_pick, fixture_pick, value_pick]},
        clubs=clubs,
        gameweeks=(gameweek,),
        rules=GameRules(
            squad_size=15,
            starting_size=11,
            club_limit=3,
            initial_budget=Money(tenths=1000),
            currency_multiplier=10,
            maximum_extra_free_transfers=4,
            squad_size_by_position={
                Position.GOALKEEPER: 2,
                Position.DEFENDER: 5,
                Position.MIDFIELDER: 5,
                Position.FORWARD: 3,
            },
            minimum_starting_by_position={
                Position.GOALKEEPER: 1,
                Position.DEFENDER: 3,
                Position.MIDFIELDER: 2,
                Position.FORWARD: 1,
            },
        ),
        retrieved_at=NOW,
    )
    snapshot = SquadSnapshot(
        gameweek=gameweek,
        picks=tuple(
            SquadPick(
                player=item,
                squad_position=index,
                multiplier=2 if index == 1 else 1 if index <= 11 else 0,
                is_captain=index == 1,
                is_vice_captain=index == 2,
            )
            for index, item in enumerate(squad_players, start=1)
        ),
        bank=Money(tenths=20),
        squad_value=Money(tenths=750),
        provenance=DataProvenance.DERIVED,
        retrieved_at=NOW,
    )
    fixtures = tuple(
        Fixture(
            id=index,
            gameweek_id=index,
            kickoff_time=None,
            home_club_id=16,
            away_club_id=17,
            home_difficulty=5,
            away_difficulty=1,
            started=False,
            finished=False,
        )
        for index in range(1, 6)
    )
    state = TransferPlanningState(
        bank=Money(tenths=20),
        free_transfers=0,
        selling_prices={outgoing.id: outgoing.current_price},
    )
    service = OnePlayerRecommendationService()

    fixture_result = service.recommend(
        squad_name="Test squad",
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        outgoing_player_id=outgoing.id,
        strategy=RecommendationStrategy.FIXTURE_FIRST,
    )
    value_result = service.recommend(
        squad_name="Test squad",
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        outgoing_player_id=outgoing.id,
        strategy=RecommendationStrategy.VALUE_FIRST,
    )

    assert fixture_result.recommendations[0].incoming.id == fixture_pick.id
    assert value_result.recommendations[0].incoming.id == value_pick.id
    assert fixture_result.score_weights.upcoming_fixtures == 0.60
    assert value_result.score_weights.value == 0.55
    assert all(item.points_hit == 4 for item in fixture_result.recommendations)


def test_no_available_legal_candidate_returns_an_explained_empty_result() -> None:
    clubs = {
        club_id: Club(id=club_id, name=f"Club {club_id}", short_name=f"C{club_id}")
        for club_id in range(1, 17)
    }
    positions = (
        [Position.GOALKEEPER] * 2
        + [Position.DEFENDER] * 5
        + [Position.MIDFIELDER] * 5
        + [Position.FORWARD] * 3
    )
    squad_players = [
        player(index, position, clubs[index]) for index, position in enumerate(positions, start=1)
    ]
    outgoing = squad_players[0]
    unavailable = player(101, Position.GOALKEEPER, clubs[16], status="i")
    gameweek = Gameweek(
        id=1,
        name="Gameweek 1",
        deadline_time=NOW,
        finished=False,
        data_checked=False,
        is_previous=False,
        is_current=False,
        is_next=True,
    )
    catalogue = FplCatalogue(
        players={item.id: item for item in squad_players + [unavailable]},
        clubs=clubs,
        gameweeks=(gameweek,),
        rules=GameRules(
            squad_size=15,
            starting_size=11,
            club_limit=3,
            initial_budget=Money(tenths=1000),
            currency_multiplier=10,
            maximum_extra_free_transfers=4,
            squad_size_by_position={
                Position.GOALKEEPER: 2,
                Position.DEFENDER: 5,
                Position.MIDFIELDER: 5,
                Position.FORWARD: 3,
            },
            minimum_starting_by_position={
                Position.GOALKEEPER: 1,
                Position.DEFENDER: 3,
                Position.MIDFIELDER: 2,
                Position.FORWARD: 1,
            },
        ),
        retrieved_at=NOW,
    )
    snapshot = SquadSnapshot(
        gameweek=gameweek,
        picks=tuple(
            SquadPick(
                player=item,
                squad_position=index,
                multiplier=2 if index == 1 else 1 if index <= 11 else 0,
                is_captain=index == 1,
                is_vice_captain=index == 2,
            )
            for index, item in enumerate(squad_players, start=1)
        ),
        bank=Money(tenths=0),
        squad_value=Money(tenths=750),
        provenance=DataProvenance.DERIVED,
        retrieved_at=NOW,
    )

    result = OnePlayerRecommendationService().recommend(
        squad_name="Test squad",
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=(),
        state=TransferPlanningState(
            bank=Money(tenths=0),
            free_transfers=1,
            selling_prices={outgoing.id: outgoing.current_price},
        ),
        outgoing_player_id=outgoing.id,
    )

    assert result.recommendations == ()
    assert result.strategy is RecommendationStrategy.BALANCED


def test_started_and_finished_fixtures_are_not_scored_as_upcoming() -> None:
    fixtures = (
        Fixture(
            id=1,
            gameweek_id=1,
            kickoff_time=NOW,
            home_club_id=1,
            away_club_id=2,
            home_difficulty=1,
            away_difficulty=5,
            started=True,
            finished=False,
        ),
        Fixture(
            id=2,
            gameweek_id=2,
            kickoff_time=NOW,
            home_club_id=1,
            away_club_id=2,
            home_difficulty=2,
            away_difficulty=4,
            started=False,
            finished=False,
        ),
    )

    difficulties = OnePlayerRecommendationService._fixture_difficulties(fixtures, horizon=5)

    assert difficulties == {1: (2,), 2: (4,)}
