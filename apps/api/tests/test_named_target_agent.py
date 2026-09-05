from datetime import UTC, datetime

import httpx
import pytest

from gaffertalk_api.domain.agent_research import (
    NamedTargetResearchRequest,
    NamedTargetResearchStatus,
)
from gaffertalk_api.domain.models import Position
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.fpl.schemas import (
    FplBootstrap,
    FplElement,
    FplElementFixture,
    FplElementHistory,
    FplElementSummary,
    FplElementType,
    FplEvent,
    FplFixture,
    FplGameSettings,
    FplTeam,
)
from gaffertalk_api.main import app, get_named_target_agent_loader
from gaffertalk_api.services.named_target_agent_loader import NamedTargetAgentLoader

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def _bootstrap(target_price: int = 95) -> FplBootstrap:
    positions = (
        [Position.GOALKEEPER] * 2
        + [Position.DEFENDER] * 5
        + [Position.MIDFIELDER] * 5
        + [Position.FORWARD] * 3
    )
    players = []
    for player_id, position in enumerate(positions, start=1):
        players.append(
            FplElement(
                id=player_id,
                web_name=f"Player {player_id}",
                team=player_id,
                element_type={
                    Position.GOALKEEPER: 1,
                    Position.DEFENDER: 2,
                    Position.MIDFIELDER: 3,
                    Position.FORWARD: 4,
                }[position],
                now_cost=90 if player_id in {3, 8, 13} else 50,
                status="a",
                total_points=30,
                minutes=450,
                starts=5,
                expected_goals=1.0,
                expected_assists=0.5,
                goals_scored=2,
                assists=1,
                bonus=3,
            )
        )
    players.append(
        FplElement(
            id=100,
            web_name="Player 100",
            first_name="Target",
            second_name="Player",
            team=100,
            element_type=4,
            now_cost=target_price,
            status="a",
            total_points=40,
            minutes=540,
            starts=6,
            expected_goals=2.2,
            expected_assists=0.8,
            goals_scored=4,
            assists=2,
            bonus=5,
        )
    )
    return FplBootstrap(
        events=[
            FplEvent(
                id=1,
                name="Gameweek 1",
                deadline_time="2026-08-21T17:30:00Z",
                finished=True,
                data_checked=True,
                is_previous=True,
            ),
            FplEvent(
                id=2,
                name="Gameweek 2",
                deadline_time="2026-08-28T17:30:00Z",
                is_next=True,
            ),
            FplEvent(
                id=3,
                name="Gameweek 3",
                deadline_time="2026-09-04T17:30:00Z",
            ),
        ],
        teams=[
            FplTeam(id=player_id, name=f"Club {player_id}", short_name=f"C{player_id}")
            for player_id in [*range(1, 16), 100]
        ],
        elements=players,
        element_types=[
            FplElementType(
                id=1,
                singular_name_short="GKP",
                squad_select=2,
                squad_min_play=1,
                squad_max_play=1,
            ),
            FplElementType(
                id=2,
                singular_name_short="DEF",
                squad_select=5,
                squad_min_play=3,
                squad_max_play=5,
            ),
            FplElementType(
                id=3,
                singular_name_short="MID",
                squad_select=5,
                squad_min_play=2,
                squad_max_play=5,
            ),
            FplElementType(
                id=4,
                singular_name_short="FWD",
                squad_select=3,
                squad_min_play=1,
                squad_max_play=3,
            ),
        ],
        game_settings=FplGameSettings(
            squad_squadplay=11,
            squad_squadsize=15,
            squad_team_limit=3,
            squad_total_spend=1000,
            ui_currency_multiplier=10,
            max_extra_free_transfers=4,
        ),
    )


def _fixture(player_id: int, fixture_id: int, *, event: int = 2) -> FplFixture:
    return FplFixture(
        id=fixture_id,
        event=event,
        kickoff_time="2026-09-12T14:00:00Z",
        team_h=player_id,
        team_a=999,
        team_h_difficulty=2,
        team_a_difficulty=4,
    )


def _summary(player_id: int) -> FplElementSummary:
    return FplElementSummary(
        fixtures=[
            FplElementFixture(
                id=1000 + player_id,
                event=2,
                kickoff_time="2026-09-12T14:00:00Z",
                team_h=player_id,
                team_a=999,
                is_home=True,
                difficulty=2,
            )
        ],
        history=[
            FplElementHistory(
                round=1,
                fixture=2000 + player_id,
                opponent_team=999,
                was_home=True,
                kickoff_time="2026-08-22T14:00:00Z",
                total_points=5,
                minutes=90,
                starts=1,
                expected_goals=0.4,
                expected_assists=0.1,
            ),
            FplElementHistory(
                round=2,
                fixture=3000 + player_id,
                opponent_team=999,
                was_home=False,
                kickoff_time="2026-08-29T14:00:00Z",
                total_points=7,
                minutes=90,
                starts=1,
                expected_goals=0.6,
                expected_assists=0.2,
            ),
        ],
        history_past=[],
    )


def _request(*, question: str) -> NamedTargetResearchRequest:
    return NamedTargetResearchRequest(
        squad={
            "name": "Test squad",
            "player_ids": list(range(1, 16)),
            "bank_tenths": 10,
            "free_transfers": 1,
        },
        selling_prices_tenths={
            player_id: 90 if player_id in {3, 8, 13} else 50 for player_id in range(1, 16)
        },
        question=question,
    )


@pytest.mark.anyio
async def test_named_target_question_runs_planner_and_evidence_end_to_end() -> None:
    bootstrap = _bootstrap()
    summaries = {player_id: _summary(player_id) for player_id in [*range(1, 16), 100]}
    global_fixtures = tuple(
        _fixture(player_id, 1000 + player_id) for player_id in [*range(1, 16), 100]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bootstrap-static/"):
            return httpx.Response(200, json=bootstrap.model_dump(mode="json"))
        if request.url.path.endswith("/fixtures/"):
            return httpx.Response(
                200, json=[fixture.model_dump(mode="json") for fixture in global_fixtures]
            )
        if "/element-summary/" in request.url.path:
            player_id = int(request.url.path.rstrip("/").split("/")[-1])
            return httpx.Response(200, json=summaries[player_id].model_dump(mode="json"))
        return httpx.Response(404)

    client = FplClient(
        client=httpx.AsyncClient(
            base_url="https://fpl.test/api/",
            transport=httpx.MockTransport(handler),
        ),
        max_attempts=1,
        clock=lambda: NOW,
    )
    try:
        report = await NamedTargetAgentLoader(client, clock=lambda: NOW).research(
            _request(
                question=(
                    "How can I get Player 100 within two Gameweeks without selling Player 1, "
                    "with a maximum total hit of eight points?"
                )
            )
        )
    finally:
        await client.aclose()

    assert report.status is NamedTargetResearchStatus.RECOMMENDATION
    assert report.target is not None and report.target.id == 100
    assert [player.id for player in report.protected_players] == [1]
    assert report.horizon_gameweek_ids == (2, 3)
    assert report.maximum_points_hit == 8
    assert report.recommended_route is not None
    assert report.recommended_route.target.id == 100
    assert len(report.alternatives) <= 2
    assert report.evidence is not None
    assert 100 in {player.player_id for player in report.evidence.players}
    assert report.evidence.freshness.value == "current"
    assert "lowest-hit legal route" in report.recommendation_reason
    assert report.strongest_objection


class StubAgentGroq:
    model = "test-agent-model"

    async def synthesize_named_target_report(self, question: str, report) -> str:
        return f"Grounded: {report.recommendation_reason}"


@pytest.mark.anyio
async def test_named_target_endpoint_returns_grounded_recommendation() -> None:
    bootstrap = _bootstrap()
    summaries = {player_id: _summary(player_id) for player_id in [*range(1, 16), 100]}
    global_fixtures = tuple(
        _fixture(player_id, 1000 + player_id) for player_id in [*range(1, 16), 100]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bootstrap-static/"):
            return httpx.Response(200, json=bootstrap.model_dump(mode="json"))
        if request.url.path.endswith("/fixtures/"):
            return httpx.Response(
                200,
                json=[fixture.model_dump(mode="json") for fixture in global_fixtures],
            )
        if "/element-summary/" in request.url.path:
            player_id = int(request.url.path.rstrip("/").split("/")[-1])
            return httpx.Response(200, json=summaries[player_id].model_dump(mode="json"))
        return httpx.Response(404)

    client = FplClient(
        client=httpx.AsyncClient(
            base_url="https://fpl.test/api/",
            transport=httpx.MockTransport(handler),
        ),
        max_attempts=1,
        clock=lambda: NOW,
    )
    app.state.groq_client = StubAgentGroq()
    app.dependency_overrides[get_named_target_agent_loader] = lambda: NamedTargetAgentLoader(
        client, clock=lambda: NOW
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            response = await http_client.post(
                "/v1/agent/research/named-target",
                json=_request(
                    question=(
                        "How can I get Player 100 within two Gameweeks without selling Player 1, "
                        "with a maximum total hit of eight points?"
                    )
                ).model_dump(mode="json"),
            )
    finally:
        app.dependency_overrides.clear()
        app.state.groq_client = None
        await client.aclose()

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["status"] == "recommendation"
    assert body["report"]["target"]["id"] == 100
    assert body["report"]["protected_players"][0]["id"] == 1
    assert body["provider"] == "groq"
    assert body["model"] == "test-agent-model"
    assert body["assistant_message"].startswith("Grounded:")


def test_unsupported_question_is_rejected_before_research() -> None:
    from gaffertalk_api.services.named_target_agent import NamedTargetAgentService

    request = _request(question="What is a link list?")
    assert not NamedTargetAgentService.has_named_target_intent(request.question)


@pytest.mark.anyio
async def test_unsupported_question_does_not_call_fpl() -> None:
    class FailingClient:
        async def get_bootstrap_observation(self):
            raise AssertionError("bootstrap should not be fetched")

        async def get_fixtures_observation(self):
            raise AssertionError("fixtures should not be fetched")

    from gaffertalk_api.services.named_target_agent_loader import NamedTargetAgentLoader

    response = await NamedTargetAgentLoader(FailingClient(), clock=lambda: NOW).research(
        _request(question="What is a link list?")
    )
    assert response.status is NamedTargetResearchStatus.UNSUPPORTED


def test_invalid_hit_limit_requires_clarification() -> None:
    from gaffertalk_api.integrations.fpl.mapper import map_catalogue
    from gaffertalk_api.services.named_target_agent import NamedTargetAgentService
    from gaffertalk_api.services.recommendation_loader import RecommendationLoader

    catalogue = map_catalogue(_bootstrap(), NOW)
    snapshot = RecommendationLoader.build_snapshot(
        _request(question="get Player 100").squad, catalogue
    )
    parsed = NamedTargetAgentService._parse_question(
        _request(question="How can I get Player 100 with a maximum hit of six?"),
        catalogue,
        snapshot,
    )
    assert parsed.clarification is not None
    assert "four-point steps" in parsed.clarification
