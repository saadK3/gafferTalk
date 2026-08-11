import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

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
from gaffertalk_api.domain.transfers import (
    ProposedTransfer,
    TransferLegalityStatus,
    TransferPlanningState,
    TransferRejectionCode,
)
from gaffertalk_api.services.transfer_legality import TransferLegalityService

FIXTURE_PATH = Path(__file__).parents[3] / "tests" / "fixtures" / "transfer-legality.scenarios.json"


def make_player(player_id: int, position: Position, club_id: int, cost: int) -> Player:
    club = Club(id=club_id, name=f"Club {club_id}", short_name=f"C{club_id}")
    return Player(
        id=player_id,
        web_name=f"Player {player_id}",
        club=club,
        position=position,
        current_price=Money(tenths=cost),
        status="a",
    )


def build_catalogue_and_snapshot() -> tuple[FplCatalogue, SquadSnapshot]:
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
    source_players = {
        1000 + index: make_player(1000 + index, position, 101 + ((index - 1) % 5), 45 + index)
        for index, position in enumerate(positions, start=1)
    }
    candidates = {
        2001: make_player(2001, Position.DEFENDER, 106, 60),
        2002: make_player(2002, Position.MIDFIELDER, 107, 60),
        2003: make_player(2003, Position.MIDFIELDER, 106, 60),
        2004: make_player(2004, Position.DEFENDER, 101, 60),
    }
    timestamp = datetime(2026, 8, 22, tzinfo=UTC)
    gameweek = Gameweek(
        id=1,
        name="Gameweek 1",
        deadline_time=datetime(2026, 8, 21, 17, 30, tzinfo=UTC),
        finished=True,
        data_checked=True,
        is_previous=True,
        is_current=False,
        is_next=False,
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
    catalogue = FplCatalogue(
        players=source_players | candidates,
        clubs={
            player.club.id: player.club
            for player in tuple(source_players.values()) + tuple(candidates.values())
        },
        gameweeks=(gameweek,),
        rules=rules,
        retrieved_at=timestamp,
    )
    snapshot = SquadSnapshot(
        gameweek=gameweek,
        picks=tuple(
            SquadPick(
                player=player,
                squad_position=index,
                multiplier=1 if index <= 11 else 0,
                is_captain=index == 8,
                is_vice_captain=index == 9,
            )
            for index, player in enumerate(source_players.values(), start=1)
        ),
        bank=Money(tenths=0),
        squad_value=Money(tenths=1000),
        provenance=DataProvenance.OBSERVED,
        retrieved_at=timestamp,
    )
    return catalogue, snapshot


def scenarios() -> list[dict[str, Any]]:
    with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


@pytest.mark.parametrize("scenario", scenarios(), ids=lambda item: str(item["name"]))
def test_canonical_transfer_legality_scenarios(scenario: dict[str, Any]) -> None:
    catalogue, snapshot = build_catalogue_and_snapshot()
    service = TransferLegalityService()
    state_payload = scenario["state"]
    state = TransferPlanningState(
        bank=Money(tenths=state_payload["bank"]) if "bank" in state_payload else None,
        free_transfers=state_payload.get("free_transfers"),
        selling_prices={
            int(player_id): Money(tenths=price)
            for player_id, price in state_payload.get("selling_prices", {}).items()
        },
        active_chip=state_payload.get("active_chip"),
    )
    result = service.validate(
        snapshot=snapshot,
        catalogue=catalogue,
        state=state,
        transfers=tuple(
            ProposedTransfer(outgoing_player_id=outgoing, incoming_player_id=incoming)
            for outgoing, incoming in scenario["transfers"]
        ),
    )

    assert result.status is TransferLegalityStatus(scenario["expected_status"])
    assert result.remaining_bank is None or result.remaining_bank.tenths == scenario.get(
        "expected_remaining_bank"
    )
    assert result.paid_transfers == scenario.get("expected_paid_transfers", 0)
    assert result.points_hit == scenario.get("expected_points_hit", 0)
    assert {rejection.code.value for rejection in result.rejections} == set(
        scenario.get("expected_codes", [])
    )


@pytest.mark.parametrize(
    ("transfers", "expected_code"),
    [
        (
            (ProposedTransfer(outgoing_player_id=9999, incoming_player_id=2001),),
            TransferRejectionCode.OUTGOING_PLAYER_NOT_IN_SQUAD,
        ),
        (
            (ProposedTransfer(outgoing_player_id=1003, incoming_player_id=9999),),
            TransferRejectionCode.UNKNOWN_INCOMING_PLAYER,
        ),
        (
            (
                ProposedTransfer(outgoing_player_id=1003, incoming_player_id=2001),
                ProposedTransfer(outgoing_player_id=1003, incoming_player_id=2002),
            ),
            TransferRejectionCode.DUPLICATE_OUTGOING_PLAYER,
        ),
        (
            (
                ProposedTransfer(outgoing_player_id=1003, incoming_player_id=2001),
                ProposedTransfer(outgoing_player_id=1008, incoming_player_id=2001),
            ),
            TransferRejectionCode.DUPLICATE_INCOMING_PLAYER,
        ),
        (
            (ProposedTransfer(outgoing_player_id=1003, incoming_player_id=1004),),
            TransferRejectionCode.INCOMING_PLAYER_ALREADY_IN_SQUAD,
        ),
    ],
)
def test_invalid_transfer_references_are_explained(
    transfers: tuple[ProposedTransfer, ...],
    expected_code: TransferRejectionCode,
) -> None:
    catalogue, snapshot = build_catalogue_and_snapshot()
    result = TransferLegalityService().validate(
        snapshot=snapshot,
        catalogue=catalogue,
        state=TransferPlanningState(bank=Money(tenths=100), free_transfers=1),
        transfers=transfers,
    )

    assert result.status is TransferLegalityStatus.ILLEGAL
    assert expected_code in {rejection.code for rejection in result.rejections}


def test_missing_bank_and_free_transfers_are_reported_together() -> None:
    catalogue, snapshot = build_catalogue_and_snapshot()
    result = TransferLegalityService().validate(
        snapshot=snapshot,
        catalogue=catalogue,
        state=TransferPlanningState(selling_prices={1003: Money(tenths=50)}),
        transfers=(ProposedTransfer(outgoing_player_id=1003, incoming_player_id=2001),),
    )

    assert result.status is TransferLegalityStatus.MISSING_STATE
    assert {rejection.code for rejection in result.rejections} == {
        TransferRejectionCode.MISSING_BANK,
        TransferRejectionCode.MISSING_FREE_TRANSFERS,
    }
