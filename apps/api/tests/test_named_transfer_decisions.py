from datetime import UTC, datetime, timedelta

import httpx
import pytest

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
from gaffertalk_api.domain.pro_research import ConfidenceLevel, ProVerdict
from gaffertalk_api.domain.recommendation_requests import NamedTransferResearchRequest
from gaffertalk_api.domain.transfers import TransferPlanningState
from gaffertalk_api.integrations.fpl.schemas import FplElementHistory, FplElementSummary
from gaffertalk_api.main import app, get_pro_research_loader
from gaffertalk_api.services.named_transfer_decisions import NamedTransferDecisionService

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def make_player(
    player_id: int,
    position: Position,
    *,
    price: int = 50,
    points: int = 25,
    starts: int = 5,
    minutes: int = 450,
    expected_goals: float = 0.4,
    expected_assists: float = 0.4,
    status: str = "a",
) -> Player:
    return Player(
        id=player_id,
        web_name=f"Player {player_id}",
        club=Club(id=player_id, name=f"Club {player_id}", short_name=f"C{player_id}"),
        position=position,
        current_price=Money(tenths=price),
        status=status,
        total_points=points,
        starts=starts,
        minutes=minutes,
        expected_goals=expected_goals,
        expected_assists=expected_assists,
        goals_scored=2,
        assists=2,
        bonus=4,
        selected_by_percent=12.5,
    )


def history(player: Player) -> FplElementSummary:
    return FplElementSummary(
        fixtures=[],
        history=[
            FplElementHistory(
                round=gameweek,
                total_points=max(0, player.total_points // 5),
                minutes=90,
                starts=1,
                expected_goals=player.expected_goals / 5,
                expected_assists=player.expected_assists / 5,
            )
            for gameweek in range(1, 6)
        ],
        history_past=[],
    )


def scenario(
    *,
    target_points: int = 50,
    target_xgi: float = 1.5,
    target_status: str = "a",
    outgoing_points: int = 20,
    include_other_risk: bool = False,
    free_transfers: int = 1,
    sample_starts: int = 5,
    alternative_points: int = 34,
    alternative_xgi: float = 1.0,
    alternative_price: int = 75,
) -> tuple[
    FplCatalogue,
    SquadSnapshot,
    tuple[Fixture, ...],
    TransferPlanningState,
    Player,
    Player,
    Player,
]:
    positions = (
        [Position.GOALKEEPER] * 2
        + [Position.DEFENDER] * 5
        + [Position.MIDFIELDER] * 5
        + [Position.FORWARD] * 3
    )
    squad = [
        make_player(
            player_id,
            position,
            price=80 if player_id == 8 else 50,
            points=outgoing_points if player_id == 8 else 25,
            starts=sample_starts,
            minutes=sample_starts * 90,
            expected_goals=0.2 if player_id == 8 else 0.4,
            expected_assists=0.3 if player_id == 8 else 0.4,
            status="i" if include_other_risk and player_id == 9 else "a",
        )
        for player_id, position in enumerate(positions, start=1)
    ]
    outgoing = squad[7]
    target = make_player(
        16,
        Position.MIDFIELDER,
        price=85,
        points=target_points,
        starts=sample_starts,
        minutes=sample_starts * 90,
        expected_goals=target_xgi / 2,
        expected_assists=target_xgi / 2,
        status=target_status,
    )
    alternative = make_player(
        17,
        Position.MIDFIELDER,
        price=alternative_price,
        points=alternative_points,
        starts=sample_starts,
        minutes=sample_starts * 90,
        expected_goals=alternative_xgi / 2,
        expected_assists=alternative_xgi / 2,
    )
    gameweek = Gameweek(
        id=6,
        name="Gameweek 6",
        deadline_time=NOW,
        finished=False,
        data_checked=False,
        is_previous=False,
        is_current=True,
        is_next=False,
    )
    players = squad + [target, alternative]
    catalogue = FplCatalogue(
        players={player.id: player for player in players},
        clubs={player.club.id: player.club for player in players},
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
        squad_value=Money(tenths=sum(player.current_price.tenths for player in squad)),
        provenance=DataProvenance.USER_SUPPLIED,
        retrieved_at=NOW,
    )
    fixtures = tuple(
        Fixture(
            id=100 * gameweek_id + index,
            gameweek_id=gameweek_id,
            kickoff_time=None,
            home_club_id=club_id,
            away_club_id=opponent_id,
            home_difficulty=difficulty,
            away_difficulty=3,
            started=False,
            finished=False,
        )
        for gameweek_id in range(6, 11)
        for index, (club_id, opponent_id, difficulty) in enumerate(
            ((outgoing.club.id, 1, 4), (target.club.id, 2, 2), (alternative.club.id, 3, 3)),
            start=1,
        )
    )
    state = TransferPlanningState(
        bank=Money(tenths=10),
        free_transfers=free_transfers,
        selling_prices={outgoing.id: outgoing.current_price},
    )
    return catalogue, snapshot, fixtures, state, outgoing, target, alternative


def run_report(*, created_at: datetime = NOW, **scenario_options: object):
    catalogue, snapshot, fixtures, state, outgoing, target, alternative = scenario(
        **scenario_options
    )
    report = NamedTransferDecisionService().research(
        squad_name="Golden squad",
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        outgoing_player_id=outgoing.id,
        target_player_id=target.id,
        histories={
            outgoing.id: history(outgoing),
            target.id: history(target),
            alternative.id: history(alternative),
        },
        created_at=created_at,
    )
    return report, outgoing, target, alternative


def test_good_named_move_returns_complete_grounded_buy_report() -> None:
    report, outgoing, target, alternative = run_report()

    assert report.schema_version == "1.0"
    assert report.verdict is ProVerdict.BUY
    assert [action.value for action in report.compared_actions] == [
        "requested_transfer",
        "hold",
        "wait",
        "alternative_transfer",
    ]
    assert report.requested_route.outgoing == outgoing
    assert report.requested_route.incoming == target
    assert report.requested_route.remaining_bank == Money(tenths=5)
    assert report.requested_route.points_hit == 0
    assert report.best_alternative.player == alternative
    assert report.case_for and report.case_against
    assert report.planning_impact
    assert report.change_conditions
    assert report.data_retrieved_at == NOW
    assert report.confidence.level is ConfidenceLevel.HIGH
    assert {item.player.id for item in report.evidence} == {8, 16, 17}
    observed = next(
        metric
        for item in report.evidence
        if item.player.id == target.id
        for metric in item.metrics
        if metric.key == "total_points"
    )
    derived = next(
        metric
        for item in report.evidence
        if item.player.id == target.id
        for metric in item.metrics
        if metric.key == "xgi_per_90"
    )
    assert observed.provenance is DataProvenance.OBSERVED
    assert derived.provenance is DataProvenance.DERIVED
    assert all(reason.id and reason.text for reason in report.grounded_reasons)


@pytest.mark.parametrize(
    ("target_points", "target_xgi", "outgoing_points", "expected"),
    [(8, 0.1, 20, ProVerdict.HOLD), (0, 0.0, 50, ProVerdict.AVOID)],
)
def test_weak_and_ambiguous_moves_do_not_receive_buy_verdict(
    target_points: int,
    target_xgi: float,
    outgoing_points: int,
    expected: ProVerdict,
) -> None:
    report, *_ = run_report(
        target_points=target_points,
        target_xgi=target_xgi,
        outgoing_points=outgoing_points,
        alternative_points=0,
    )
    assert report.verdict is expected
    assert report.best_alternative.action.value in {"hold", "alternative_transfer"}


def test_points_hit_is_explicit_and_reduces_the_requested_case() -> None:
    report, *_ = run_report(target_points=36, target_xgi=1.0, free_transfers=0)
    assert report.requested_route.points_hit == 4
    assert report.opportunity_cost.points_hit == 4
    assert any("4-point hit" in reason for reason in report.case_against)


def test_other_unavailable_squad_player_is_a_more_urgent_priority() -> None:
    report, *_ = run_report(include_other_risk=True)
    assert report.squad_priority.more_urgent is True
    assert report.squad_priority.player is not None
    assert report.squad_priority.player.id == 9
    assert report.verdict is ProVerdict.WAIT
    assert "Player 9 first" in report.recommended_action


def test_stronger_legal_alternative_overturns_requested_buy() -> None:
    report, _, _, alternative = run_report(alternative_points=80, alternative_xgi=4.0)
    assert report.verdict is ProVerdict.AVOID
    assert report.best_alternative.player == alternative
    assert alternative.web_name in report.recommended_action


def test_unavailable_target_and_missing_selling_price_are_actionable_failures() -> None:
    catalogue, snapshot, fixtures, state, outgoing, target, alternative = scenario(
        target_status="i"
    )
    service = NamedTransferDecisionService()
    with pytest.raises(ValueError, match="not currently marked available"):
        service.research(
            squad_name="Golden squad",
            snapshot=snapshot,
            catalogue=catalogue,
            fixtures=fixtures,
            state=state,
            outgoing_player_id=outgoing.id,
            target_player_id=target.id,
            histories={outgoing.id: history(outgoing), target.id: history(target)},
            created_at=NOW,
        )

    missing_price = state.model_copy(update={"selling_prices": {}})
    available_target = target.model_copy(update={"status": "a"})
    available_catalogue = catalogue.model_copy(
        update={"players": {**catalogue.players, target.id: available_target}}
    )
    with pytest.raises(ValueError, match="selling price"):
        service.research(
            squad_name="Golden squad",
            snapshot=snapshot,
            catalogue=available_catalogue,
            fixtures=fixtures,
            state=missing_price,
            outgoing_player_id=outgoing.id,
            target_player_id=target.id,
            histories={outgoing.id: history(outgoing), target.id: history(target)},
            created_at=NOW,
        )


def test_early_sample_is_low_confidence_and_exposes_freshness() -> None:
    report, *_ = run_report(target_points=8, target_xgi=0.2, sample_starts=1)
    assert report.confidence.level is ConfidenceLevel.LOW
    assert report.data_retrieved_at == NOW
    assert all(item.source_retrieved_at == NOW for item in report.evidence)


def test_stale_evidence_forces_low_confidence() -> None:
    report, *_ = run_report(created_at=NOW + timedelta(hours=2))
    assert report.confidence.level is ConfidenceLevel.LOW
    assert "older than" in report.confidence.reasons[0]


class StubProResearchLoader:
    async def named_transfer(self, request: NamedTransferResearchRequest):
        report, *_ = run_report()
        return report


class StubProGroq:
    model = "test-pro-model"

    async def synthesize_pro_report(self, question: str, report):
        return f"Grounded: {report.recommended_action}"


class FailingProGroq(StubProGroq):
    async def synthesize_pro_report(self, question: str, report):
        request = httpx.Request("POST", "https://groq.test/chat/completions")
        raise httpx.ConnectError("unavailable", request=request)


def pro_request_payload() -> dict[str, object]:
    return {
        "squad": {
            "name": "Golden squad",
            "player_ids": list(range(1, 16)),
            "bank_tenths": 10,
            "free_transfers": 1,
        },
        "outgoing_player_id": 8,
        "outgoing_selling_price_tenths": 80,
        "target_player_id": 16,
        "question": "Should I sell Player 8 for Player 16?",
    }


@pytest.mark.anyio
async def test_named_transfer_endpoint_returns_versioned_grounded_report() -> None:
    app.state.groq_client = StubProGroq()
    app.dependency_overrides[get_pro_research_loader] = lambda: StubProResearchLoader()
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/pro/research/named-transfer",
                json=pro_request_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["schema_version"] == "1.0"
    assert body["report"]["verdict"] == "buy"
    assert body["report"]["requested_route"]["incoming"]["id"] == 16
    assert body["report"]["confidence"]["policy_version"] == "1.0"
    assert body["assistant_message"].startswith("Grounded:")
    assert body["provider"] == "groq"


@pytest.mark.anyio
async def test_provider_failure_returns_non_success_without_fallback_report() -> None:
    app.state.groq_client = FailingProGroq()
    app.dependency_overrides[get_pro_research_loader] = lambda: StubProResearchLoader()
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/pro/research/named-transfer",
                json=pro_request_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "pro_research_unavailable"
    assert "report" not in response.json()
