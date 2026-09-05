from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from gaffertalk_api.domain.models import (
    Club,
    DataProvenance,
    FplCatalogue,
    GameRules,
    Gameweek,
    Money,
    Player,
    Position,
    SquadPick,
    SquadSnapshot,
)
from gaffertalk_api.domain.multi_gameweek_planning import (
    MultiGameweekPlanningState,
    MultiGameweekRouteRequest,
    MultiGameweekSearchStatus,
    RollAction,
    SellingPriceBasis,
)
from gaffertalk_api.services.multi_gameweek_routes import MultiGameweekRouteService

NOW = datetime(2026, 9, 4, tzinfo=UTC)


def player(player_id: int, position: Position, price: int) -> Player:
    club = Club(id=player_id, name=f"Club {player_id}", short_name=f"C{player_id}")
    return Player(
        id=player_id,
        web_name=f"Player {player_id}",
        club=club,
        position=position,
        current_price=Money(tenths=price),
        status="a",
    )


def scenario(*, target_price: int = 150) -> tuple[FplCatalogue, SquadSnapshot, Player]:
    positions = (
        Position.GOALKEEPER,
        Position.GOALKEEPER,
        Position.DEFENDER,
        Position.DEFENDER,
        Position.DEFENDER,
        Position.DEFENDER,
        Position.DEFENDER,
        Position.MIDFIELDER,
        Position.MIDFIELDER,
        Position.MIDFIELDER,
        Position.MIDFIELDER,
        Position.MIDFIELDER,
        Position.FORWARD,
        Position.FORWARD,
        Position.FORWARD,
    )
    squad = {
        index: player(index, position, 50) for index, position in enumerate(positions, start=1)
    }
    squad[3] = player(3, Position.DEFENDER, 70)
    squad[8] = player(8, Position.MIDFIELDER, 90)
    squad[13] = player(13, Position.FORWARD, 90)
    target = player(100, Position.FORWARD, target_price)
    candidates = {
        101: player(101, Position.MIDFIELDER, 30),
        102: player(102, Position.DEFENDER, 30),
        103: player(103, Position.MIDFIELDER, 35),
        104: player(104, Position.DEFENDER, 35),
        105: player(105, Position.FORWARD, 25),
    }
    gameweeks = tuple(
        Gameweek(
            id=gameweek_id,
            name=f"Gameweek {gameweek_id}",
            deadline_time=datetime(2026, 9, 4 + 7 * gameweek_id, tzinfo=UTC),
            finished=gameweek_id == 1,
            data_checked=gameweek_id == 1,
            is_previous=gameweek_id == 1,
            is_current=False,
            is_next=gameweek_id == 2,
        )
        for gameweek_id in (1, 2, 3)
    )
    rules = GameRules(
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
    )
    all_players = squad | {target.id: target} | candidates
    catalogue = FplCatalogue(
        players=all_players,
        clubs={item.club.id: item.club for item in all_players.values()},
        gameweeks=gameweeks,
        rules=rules,
        retrieved_at=NOW,
    )
    snapshot = SquadSnapshot(
        gameweek=gameweeks[0],
        picks=tuple(
            SquadPick(
                player=item,
                squad_position=index,
                multiplier=1 if index <= 11 else 0,
                is_captain=index == 8,
                is_vice_captain=index == 9,
            )
            for index, item in enumerate(squad.values(), start=1)
        ),
        bank=Money(tenths=10),
        squad_value=Money(tenths=900),
        provenance=DataProvenance.OBSERVED,
        retrieved_at=NOW,
    )
    return catalogue, snapshot, target


def request_for(
    catalogue: FplCatalogue,
    snapshot: SquadSnapshot,
    *,
    selling_prices: dict[int, int] | None = None,
    horizon: tuple[int, ...] = (2, 3),
    protected: tuple[int, ...] = (),
    maximum_hit: int = 8,
    bank: int = 10,
    free_transfers: int = 1,
) -> MultiGameweekRouteRequest:
    return MultiGameweekRouteRequest(
        state=MultiGameweekPlanningState(
            snapshot=snapshot,
            bank=Money(tenths=bank),
            free_transfers=free_transfers,
            selling_prices={
                player_id: Money(tenths=price)
                for player_id, price in (selling_prices or {}).items()
            },
        ),
        target_player_id=100,
        horizon_gameweek_ids=horizon,
        protected_player_ids=protected,
        maximum_points_hit=maximum_hit,
    )


def all_selling_prices(snapshot: SquadSnapshot) -> dict[int, int]:
    return {pick.player.id: pick.player.current_price.tenths for pick in snapshot.picks}


def test_affordable_target_has_a_direct_current_gameweek_route() -> None:
    catalogue, snapshot, _ = scenario(target_price=95)
    report = MultiGameweekRouteService().search(
        request=request_for(
            catalogue,
            snapshot,
            selling_prices=all_selling_prices(snapshot),
            horizon=(2,),
            maximum_hit=0,
        ),
        catalogue=catalogue,
    )

    assert report.status is MultiGameweekSearchStatus.ROUTES
    assert report.primary_route is not None
    assert report.primary_route.target_arrival_gameweek_id == 2
    assert report.primary_route.total_transfers == 1
    assert report.primary_route.total_points_hit == 0
    assert report.primary_route.remaining_bank == Money(tenths=5)
    assert 100 in report.primary_route.resulting_player_ids


def test_rolling_makes_a_two_transfer_route_free() -> None:
    catalogue, snapshot, _ = scenario(target_price=150)
    report = MultiGameweekRouteService().search(
        request=request_for(
            catalogue,
            snapshot,
            selling_prices=all_selling_prices(snapshot),
            maximum_hit=0,
        ),
        catalogue=catalogue,
    )

    assert report.status is MultiGameweekSearchStatus.ROUTES
    assert report.primary_route is not None
    assert report.primary_route.total_transfers == 2
    assert report.primary_route.total_points_hit == 0
    assert report.primary_route.target_arrival_gameweek_id == 3
    assert isinstance(report.primary_route.steps[0].action, RollAction)
    assert report.primary_route.steps[0].free_transfers_next_gameweek == 2
    assert report.primary_route.steps[1].free_transfers_used == 2


def test_three_transfer_route_costs_four_points_after_rolling() -> None:
    catalogue, snapshot, _ = scenario(target_price=190)
    report = MultiGameweekRouteService().search(
        request=request_for(
            catalogue,
            snapshot,
            selling_prices=all_selling_prices(snapshot),
            maximum_hit=4,
        ),
        catalogue=catalogue,
    )

    assert report.status is MultiGameweekSearchStatus.ROUTES
    assert report.primary_route is not None
    assert report.primary_route.total_transfers == 3
    assert report.primary_route.total_points_hit == 4
    assert sum(step.points_hit for step in report.primary_route.steps) == 4
    assert report.primary_route.steps[-1].free_transfers_next_gameweek == 1


def test_missing_selling_prices_make_the_lead_route_provisional() -> None:
    catalogue, snapshot, _ = scenario(target_price=150)
    service = MultiGameweekRouteService()
    preliminary = service.search(
        request=request_for(catalogue, snapshot, selling_prices={}),
        catalogue=catalogue,
    )

    assert preliminary.status is MultiGameweekSearchStatus.NEEDS_SELLING_PRICES
    assert preliminary.primary_route is not None
    requested = set(preliminary.requested_selling_price_player_ids)
    route_outgoing = {
        transfer.outgoing.id
        for step in preliminary.primary_route.steps
        for transfer in step.transfers
    }
    assert requested == route_outgoing
    assert requested
    assert all(
        transfer.selling_price_basis is SellingPriceBasis.CURRENT_PRICE_UPPER_BOUND
        for step in preliminary.primary_route.steps
        for transfer in step.transfers
    )

    confirmed = service.search(
        request=request_for(
            catalogue,
            snapshot,
            selling_prices={
                player_id: catalogue.players[player_id].current_price.tenths
                for player_id in requested
            },
        ),
        catalogue=catalogue,
    )
    assert confirmed.status is MultiGameweekSearchStatus.ROUTES
    assert not confirmed.requested_selling_price_player_ids


def test_protected_target_position_players_prove_no_legal_route() -> None:
    catalogue, snapshot, _ = scenario()
    report = MultiGameweekRouteService().search(
        request=request_for(
            catalogue,
            snapshot,
            protected=(13, 14, 15),
        ),
        catalogue=catalogue,
    )

    assert report.status is MultiGameweekSearchStatus.NO_LEGAL_ROUTE
    assert report.primary_route is None
    assert report.stats.route_simulations == 0


def test_hit_limit_failure_is_only_no_route_within_search_bounds() -> None:
    catalogue, snapshot, _ = scenario(target_price=190)
    report = MultiGameweekRouteService().search(
        request=request_for(
            catalogue,
            snapshot,
            selling_prices=all_selling_prices(snapshot),
            maximum_hit=0,
        ),
        catalogue=catalogue,
    )

    assert report.status is MultiGameweekSearchStatus.NO_ROUTE_FOUND_WITHIN_BOUNDS
    assert report.primary_route is None
    assert report.stats.route_simulations > 0


def test_target_already_owned_is_distinct_from_route_failure() -> None:
    catalogue, snapshot, target = scenario()
    updated_picks = tuple(
        pick.model_copy(update={"player": target}) if pick.player.id == 13 else pick
        for pick in snapshot.picks
    )
    snapshot = snapshot.model_copy(update={"picks": updated_picks})
    report = MultiGameweekRouteService().search(
        request=request_for(catalogue, snapshot),
        catalogue=catalogue,
    )

    assert report.status is MultiGameweekSearchStatus.TARGET_ALREADY_OWNED
    assert report.primary_route is None


def test_request_rejects_invalid_context_before_search() -> None:
    catalogue, snapshot, _ = scenario()
    with pytest.raises(ValidationError, match="protected players must belong"):
        request_for(catalogue, snapshot, protected=(999,))

    with pytest.raises(ValidationError, match="planning Gameweeks must be ordered"):
        request_for(catalogue, snapshot, horizon=(3, 2))

    with pytest.raises(ValueError, match="must be consecutive"):
        MultiGameweekRouteService().search(
            request=request_for(catalogue, snapshot, horizon=(1, 3)),
            catalogue=catalogue,
        )

    with pytest.raises(ValueError, match="Gameweek after the confirmed snapshot"):
        MultiGameweekRouteService().search(
            request=request_for(catalogue, snapshot, horizon=(1, 2)),
            catalogue=catalogue,
        )

    missing_player_catalogue = catalogue.model_copy(
        update={"players": {key: value for key, value in catalogue.players.items() if key != 1}}
    )
    with pytest.raises(ValueError, match="every squad player"):
        MultiGameweekRouteService().search(
            request=request_for(catalogue, snapshot),
            catalogue=missing_player_catalogue,
        )


def test_search_is_deterministic_and_exposes_its_bounds() -> None:
    catalogue, snapshot, _ = scenario(target_price=190)
    request = request_for(
        catalogue,
        snapshot,
        selling_prices=all_selling_prices(snapshot),
        maximum_hit=8,
    )
    service = MultiGameweekRouteService()

    first = service.search(request=request, catalogue=catalogue)
    second = service.search(request=request, catalogue=catalogue)

    assert first == second
    assert first.bounds.maximum_gameweeks == 2
    assert first.bounds.maximum_total_transfers == 3
    assert first.stats.route_simulations <= first.bounds.maximum_route_simulations
    assert "not a football-performance recommendation" in first.selection_basis
    assert len(first.alternatives) <= 2
