from datetime import UTC, datetime

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
from gaffertalk_api.domain.recommendation_requests import ConversationOutcome
from gaffertalk_api.domain.transfers import TransferPlanningState
from gaffertalk_api.services.conversation_preflight import ConversationPreflightService

NOW = datetime(2026, 8, 21, 17, 30, tzinfo=UTC)


def setup() -> tuple[FplCatalogue, SquadSnapshot, TransferPlanningState]:
    clubs = {
        club_id: Club(id=club_id, name=f"Club {club_id}", short_name=f"C{club_id}")
        for club_id in range(1, 20)
    }
    positions = (
        [Position.GOALKEEPER] * 2
        + [Position.DEFENDER] * 5
        + [Position.MIDFIELDER] * 5
        + [Position.FORWARD] * 3
    )
    squad = [
        Player(
            id=index,
            web_name=(
                "B.Fernandes" if index == 8 else "Haaland" if index == 13 else f"Player {index}"
            ),
            first_name="Bruno" if index == 8 else "Erling" if index == 13 else "",
            second_name="Fernandes" if index == 8 else "Haaland" if index == 13 else "",
            club=clubs[1 if index <= 3 else index],
            position=position,
            current_price=Money(tenths=50),
            status="a",
        )
        for index, position in enumerate(positions, start=1)
    ]
    targets = (
        Player(
            id=16,
            web_name="Isak",
            club=clubs[16],
            position=Position.FORWARD,
            current_price=Money(tenths=90),
            status="a",
        ),
        Player(
            id=17,
            web_name="Saka",
            club=clubs[17],
            position=Position.MIDFIELDER,
            current_price=Money(tenths=55),
            status="a",
        ),
        Player(
            id=18,
            web_name="Premium",
            club=clubs[18],
            position=Position.MIDFIELDER,
            current_price=Money(tenths=100),
            status="a",
        ),
        Player(
            id=19,
            web_name="Injured",
            club=clubs[19],
            position=Position.MIDFIELDER,
            current_price=Money(tenths=50),
            status="i",
        ),
        Player(
            id=20,
            web_name="Fourth",
            club=clubs[1],
            position=Position.MIDFIELDER,
            current_price=Money(tenths=50),
            status="a",
        ),
        Player(
            id=21,
            web_name="Fernandes",
            first_name="Mateus",
            second_name="Fernandes",
            club=clubs[19],
            position=Position.MIDFIELDER,
            current_price=Money(tenths=60),
            status="a",
        ),
    )
    gameweek = Gameweek(
        id=1,
        name="Gameweek 1",
        deadline_time=NOW,
        finished=False,
        data_checked=False,
        is_previous=False,
        is_current=True,
        is_next=False,
    )
    catalogue = FplCatalogue(
        players={player.id: player for player in [*squad, *targets]},
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
                player=player,
                squad_position=index,
                multiplier=2 if index == 1 else 1 if index <= 11 else 0,
                is_captain=index == 1,
                is_vice_captain=index == 2,
            )
            for index, player in enumerate(squad, start=1)
        ),
        bank=Money(tenths=10),
        squad_value=Money(tenths=750),
        provenance=DataProvenance.USER_SUPPLIED,
        retrieved_at=NOW,
    )
    state = TransferPlanningState(
        bank=Money(tenths=10),
        free_transfers=1,
        selling_prices={8: Money(tenths=50)},
    )
    return catalogue, snapshot, state


def preflight(question: str):
    catalogue, snapshot, state = setup()
    return ConversationPreflightService().validate(
        question=question,
        outgoing_player_id=8,
        snapshot=snapshot,
        catalogue=catalogue,
        state=state,
    )


def test_misspelled_owned_target_is_resolved_without_groq() -> None:
    result = preflight("How can I get Halaand into my team?")

    assert result.outcome is ConversationOutcome.ALREADY_OWNED
    assert result.target is not None and result.target.web_name == "Haaland"
    assert "already in your current squad" in (result.message or "")


def test_position_mismatch_and_unknown_target_are_actionable() -> None:
    mismatch = preflight("How can I get Isak into my team?")
    unknown = preflight("How can I get Mboppe into my team?")

    assert mismatch.outcome is ConversationOutcome.POSITION_MISMATCH
    assert "select one of your FWD players" in (mismatch.message or "")
    assert unknown.outcome is ConversationOutcome.TARGET_NOT_FOUND


def test_legal_target_continues_but_invalid_targets_stop() -> None:
    legal = preflight("Can I replace Bruno Fernandes with Saka?")
    legal_natural = preflight("Is Saka a good replacement?")
    unaffordable = preflight("Can I get Premium into my team?")
    unavailable = preflight("Can I get Injured into my team?")
    club_limit = preflight("Can I get Fourth into my team?")
    generic = preflight("Who is the best replacement based on fixtures?")
    outgoing_mention = preflight("Who is the best replacement for Bruno Fernandes?")

    assert legal.can_recommend and legal.target is not None and legal.target.web_name == "Saka"
    assert legal_natural.can_recommend
    assert legal_natural.target is not None and legal_natural.target.web_name == "Saka"
    assert unaffordable.outcome is ConversationOutcome.TARGET_ILLEGAL
    assert "£4.0m short" in (unaffordable.message or "")
    assert unavailable.outcome is ConversationOutcome.TARGET_UNAVAILABLE
    assert club_limit.outcome is ConversationOutcome.TARGET_ILLEGAL
    assert "three-player limit" in (club_limit.message or "")
    assert generic.can_recommend and generic.target is None
    assert outgoing_mention.can_recommend and outgoing_mention.target is None


def test_auto_route_finds_outgoing_player_and_requires_real_selling_price() -> None:
    catalogue, snapshot, _ = setup()

    result = ConversationPreflightService().discover_route(
        question="What is the best way to get Saka into my squad?",
        snapshot=snapshot,
        catalogue=catalogue,
        bank_tenths=10,
        free_transfers=1,
    )

    assert result.outcome is ConversationOutcome.SELLING_PRICE_REQUIRED
    assert result.target is not None and result.target.web_name == "Saka"
    assert result.suggested_outgoing is not None
    assert result.suggested_outgoing.position is Position.MIDFIELDER
    assert "actual selling price" in (result.message or "")


def test_auto_route_requires_an_explicit_target() -> None:
    catalogue, snapshot, _ = setup()

    result = ConversationPreflightService().discover_route(
        question="Who should I transfer this week?",
        snapshot=snapshot,
        catalogue=catalogue,
        bank_tenths=10,
        free_transfers=1,
    )

    assert result.outcome is ConversationOutcome.TARGET_REQUIRED
    assert result.suggested_outgoing is None
