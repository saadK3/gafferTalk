import httpx
import pytest
from test_named_target_agent import NOW, _bootstrap, _fixture, _request, _summary

from gaffertalk_api.domain.general_research import (
    GeneralResearchRequest,
    GeneralResearchStatus,
    ResearchCapability,
)
from gaffertalk_api.domain.player_evidence import EvidenceNature
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.main import app, get_general_research_agent
from gaffertalk_api.services.general_research_agent import GeneralResearchAgent


def _client() -> FplClient:
    bootstrap = _bootstrap()
    fixtures = tuple(_fixture(player_id, 1000 + player_id) for player_id in [*range(1, 16), 100])
    summaries = {player_id: _summary(player_id) for player_id in [*range(1, 16), 100]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bootstrap-static/"):
            return httpx.Response(200, json=bootstrap.model_dump(mode="json"))
        if request.url.path.endswith("/fixtures/"):
            return httpx.Response(
                200,
                json=[fixture.model_dump(mode="json") for fixture in fixtures],
            )
        if "/element-summary/" in request.url.path:
            player_id = int(request.url.path.rstrip("/").split("/")[-1])
            return httpx.Response(200, json=summaries[player_id].model_dump(mode="json"))
        return httpx.Response(404)

    return FplClient(
        client=httpx.AsyncClient(
            base_url="https://fpl.test/api/",
            transport=httpx.MockTransport(handler),
        ),
        max_attempts=1,
        clock=lambda: NOW,
    )


def test_router_handles_questions_not_used_in_prompt_examples() -> None:
    assert (
        GeneralResearchAgent.classify("Could I raise enough money to bring in Watkins?")
        is ResearchCapability.BUDGET_RELEASE
    )
    assert (
        GeneralResearchAgent.classify("Would keeping my free transfer be wiser than acting now?")
        is ResearchCapability.HOLD_OR_TRANSFER
    )
    assert (
        GeneralResearchAgent.classify("Which midfielders have the steadiest recent starts?")
        is ResearchCapability.HISTORICAL_ALTERNATIVES
    )
    assert (
        GeneralResearchAgent.classify("Which keepers have the most reliable minutes?")
        is ResearchCapability.HISTORICAL_ALTERNATIVES
    )
    assert (
        GeneralResearchAgent.classify("What parts of my squad need attention before the deadline?")
        is ResearchCapability.SQUAD_CONCERNS
    )
    assert (
        GeneralResearchAgent.classify("Who won the match last night?")
        is ResearchCapability.UNSUPPORTED
    )


@pytest.mark.anyio
async def test_historical_alternatives_do_not_require_private_team_state() -> None:
    client = _client()
    try:
        report = await GeneralResearchAgent(client, clock=lambda: NOW).research(
            GeneralResearchRequest(
                question=(
                    "Which midfielders have similar historical output but more consistent recent "
                    "minutes?"
                )
            )
        )
    finally:
        await client.aclose()

    assert report.capability is ResearchCapability.HISTORICAL_ALTERNATIVES
    assert report.status is GeneralResearchStatus.RECOMMENDATION
    assert report.subject is None
    assert report.alternatives
    assert report.evidence is not None
    assert all(
        fact.nature in {EvidenceNature.OBSERVED, EvidenceNature.CALCULATED} for fact in report.facts
    )
    assert all("forecast" not in fact.value.casefold() for fact in report.facts)
    assert "future points" in report.strongest_objection


@pytest.mark.anyio
async def test_named_subject_alternatives_include_a_historical_baseline() -> None:
    client = _client()
    try:
        report = await GeneralResearchAgent(client, clock=lambda: NOW).research(
            GeneralResearchRequest(
                question="Which defenders are alternatives to Player 3 with more minutes?"
            )
        )
    finally:
        await client.aclose()

    assert report.subject is not None and report.subject.id == 3
    assert report.evidence is not None
    assert 3 in {item.player_id for item in report.evidence.players}
    assert any(fact.subject == "Player 3" for fact in report.facts)


@pytest.mark.anyio
async def test_budget_release_routes_through_named_target_planner() -> None:
    client = _client()
    try:
        source = _request(question="get Player 100")
        report = await GeneralResearchAgent(client, clock=lambda: NOW).research(
            GeneralResearchRequest(
                squad=source.squad,
                selling_prices_tenths=source.selling_prices_tenths,
                question="How can I free up budget for Player 100?",
            )
        )
    finally:
        await client.aclose()

    assert report.capability is ResearchCapability.BUDGET_RELEASE
    assert report.status is GeneralResearchStatus.RECOMMENDATION
    assert report.subject is not None and report.subject.id == 100
    assert report.named_target_report is not None
    assert report.route_report is not None
    assert report.calculations


@pytest.mark.anyio
async def test_squad_concerns_route_through_whole_squad_research() -> None:
    client = _client()
    try:
        source = _request(question="get Player 100")
        report = await GeneralResearchAgent(client, clock=lambda: NOW).research(
            GeneralResearchRequest(
                squad=source.squad,
                selling_prices_tenths=source.selling_prices_tenths,
                question="What parts of my squad need attention before the deadline?",
            )
        )
    finally:
        await client.aclose()

    assert report.capability is ResearchCapability.SQUAD_CONCERNS
    assert report.status is GeneralResearchStatus.RECOMMENDATION
    assert report.subject is not None
    assert report.squad_action_report is not None
    assert report.facts


@pytest.mark.anyio
async def test_hold_question_compares_action_with_rolling() -> None:
    client = _client()
    try:
        source = _request(question="get Player 100")
        report = await GeneralResearchAgent(client, clock=lambda: NOW).research(
            GeneralResearchRequest(
                squad=source.squad,
                selling_prices_tenths=source.selling_prices_tenths,
                question="Would keeping my free transfer be wiser than acting now?",
            )
        )
    finally:
        await client.aclose()

    assert report.capability is ResearchCapability.HOLD_OR_TRANSFER
    assert report.status is GeneralResearchStatus.RECOMMENDATION
    assert report.squad_action_report is not None
    assert len(report.squad_action_report.compared_actions) >= 2


class StubGeneralGroq:
    model = "test-general-model"

    async def synthesize_general_report(self, question: str, report) -> str:
        return f"Grounded: {report.recommended_action}"


@pytest.mark.anyio
async def test_general_endpoint_routes_and_synthesizes_alternative_question() -> None:
    client = _client()
    app.state.groq_client = StubGeneralGroq()
    app.dependency_overrides[get_general_research_agent] = lambda: GeneralResearchAgent(
        client, clock=lambda: NOW
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            response = await http_client.post(
                "/v1/agent/research",
                json={
                    "question": (
                        "Which midfielders have similar historical output but more consistent "
                        "recent minutes?"
                    )
                },
            )
    finally:
        app.dependency_overrides.clear()
        app.state.groq_client = None
        await client.aclose()

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["capability"] == "historical_alternatives"
    assert body["report"]["status"] == "recommendation"
    assert body["provider"] == "groq"
    assert body["assistant_message"].startswith("Grounded:")


@pytest.mark.anyio
async def test_unsupported_and_missing_state_stop_before_fpl_calls() -> None:
    class FailingClient:
        async def get_bootstrap_observation(self):
            raise AssertionError("bootstrap should not be fetched")

        async def get_fixtures_observation(self):
            raise AssertionError("fixtures should not be fetched")

    agent = GeneralResearchAgent(FailingClient())  # type: ignore[arg-type]
    unsupported = await agent.research(
        GeneralResearchRequest(question="Who won the match last night?")
    )
    missing_state = await agent.research(
        GeneralResearchRequest(question="Would keeping my free transfer be wiser than acting now?")
    )
    assert unsupported.status is GeneralResearchStatus.UNSUPPORTED
    assert missing_state.status is GeneralResearchStatus.NEEDS_CLARIFICATION
    assert missing_state.clarification_question is not None
