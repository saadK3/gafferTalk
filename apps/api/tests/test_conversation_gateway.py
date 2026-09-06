import httpx
import pytest
from test_general_research_agent import NOW, _client, _request

from gaffertalk_api.domain.conversation_gateway import (
    ConversationIntent,
    ConversationIntentStatus,
    ConversationResponseStatus,
    ConversationTurnRequest,
)
from gaffertalk_api.domain.general_research import ResearchCapability
from gaffertalk_api.main import app, get_conversation_gateway
from gaffertalk_api.services.conversation_gateway import ConversationGateway
from gaffertalk_api.services.general_research_agent import GeneralResearchAgent
from gaffertalk_api.services.player_catalogue import PlayerCatalogueLoader


def ready_intent(
    capability: ResearchCapability,
    *,
    target_player_name: str | None = None,
    protected_player_names: tuple[str, ...] = (),
) -> ConversationIntent:
    return ConversationIntent(
        capability=capability,
        status=ConversationIntentStatus.READY,
        target_player_name=target_player_name,
        protected_player_names=protected_player_names,
        explanation=f"The question is about {capability.value.replace('_', ' ')}.",
    )


def clarification_intent(
    capability: ResearchCapability,
    *,
    missing: tuple[str, ...],
) -> ConversationIntent:
    question = "Please provide the missing information."
    return ConversationIntent(
        capability=capability,
        status=ConversationIntentStatus.NEEDS_CLARIFICATION,
        missing_information=missing,
        clarification_question=question,
        explanation=question,
    )


class StubInterpreter:
    model = "test-interpreter"

    def __init__(self, *intents: ConversationIntent) -> None:
        self._intents = list(intents)
        self.questions: list[str] = []

    async def interpret_general_question(self, question, *, squad, history):
        self.questions.append(question)
        return self._intents.pop(0)

    async def synthesize_general_report(self, question, report):
        return f"Grounded: {report.recommended_action}"


@pytest.mark.anyio
async def test_roll_wording_is_understood_by_deterministic_fallback() -> None:
    client = _client()
    source = _request(question="get Player 100")
    try:
        gateway = ConversationGateway(
            GeneralResearchAgent(client, clock=lambda: NOW),
            PlayerCatalogueLoader(client),
            clock=lambda: NOW,
        )
        response = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="roll-fallback",
                question="Should I roll my free transfer or make a transfer this week?",
                squad=source.squad,
                selling_prices_tenths=source.selling_prices_tenths,
            )
        )
    finally:
        await client.aclose()

    assert response.status is ConversationResponseStatus.ANSWERED
    assert response.intent.capability is ResearchCapability.HOLD_OR_TRANSFER
    assert response.research is not None


@pytest.mark.anyio
async def test_clear_supported_phrase_overrides_model_unsupported_label() -> None:
    client = _client()
    source = _request(question="get Player 100")
    interpreter = StubInterpreter(
        ConversationIntent(
            capability=ResearchCapability.UNSUPPORTED,
            status=ConversationIntentStatus.UNSUPPORTED,
            explanation="The model did not recognise the phrase.",
        )
    )
    try:
        gateway = ConversationGateway(
            GeneralResearchAgent(client, clock=lambda: NOW),
            PlayerCatalogueLoader(client),
            interpreter=interpreter,
            clock=lambda: NOW,
        )
        response = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="model-unsupported-roll",
                question="What if I roll my free transfer this week?",
                squad=source.squad,
                selling_prices_tenths=source.selling_prices_tenths,
            )
        )
    finally:
        await client.aclose()

    assert response.status is ConversationResponseStatus.ANSWERED
    assert response.intent.capability is ResearchCapability.HOLD_OR_TRANSFER
    assert response.research is not None


@pytest.mark.anyio
async def test_gateway_preserves_context_for_a_follow_up_turn() -> None:
    client = _client()
    source = _request(question="get Player 100")
    interpreter = StubInterpreter(
        ready_intent(ResearchCapability.HOLD_OR_TRANSFER),
        ready_intent(ResearchCapability.HOLD_OR_TRANSFER),
    )
    try:
        gateway = ConversationGateway(
            GeneralResearchAgent(client, clock=lambda: NOW),
            PlayerCatalogueLoader(client),
            interpreter=interpreter,
            clock=lambda: NOW,
        )
        first = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="follow-up",
                question="Should I hold or transfer?",
                squad=source.squad,
                selling_prices_tenths=source.selling_prices_tenths,
            )
        )
        second = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="follow-up",
                question="What if I wait one more week?",
            )
        )
    finally:
        await client.aclose()

    assert first.status is ConversationResponseStatus.ANSWERED
    assert second.status is ConversationResponseStatus.ANSWERED
    assert second.research is not None
    assert len(interpreter.questions) == 2


@pytest.mark.anyio
async def test_gateway_asks_for_required_team_state_before_research() -> None:
    interpreter = StubInterpreter(ready_intent(ResearchCapability.HOLD_OR_TRANSFER))

    class FailingCatalogue:
        async def load(self):
            raise AssertionError("a missing-state question should not load FPL data")

    class FailingAgent:
        async def research(self, request):
            raise AssertionError("research should not run without squad state")

        def response(self, report, *, assistant_message, provider, model):
            raise AssertionError("research should not be rendered")

    gateway = ConversationGateway(
        FailingAgent(),  # type: ignore[arg-type]
        FailingCatalogue(),  # type: ignore[arg-type]
        interpreter=interpreter,
    )
    response = await gateway.handle(
        ConversationTurnRequest(
            conversation_id="missing-state",
            question="Should I roll or transfer?",
        )
    )

    assert response.status is ConversationResponseStatus.NEEDS_CLARIFICATION
    assert response.research is None
    assert "15-player squad" in response.assistant_message


@pytest.mark.anyio
async def test_gateway_asks_for_hit_limit_on_a_multi_gameweek_route() -> None:
    client = _client()
    source = _request(question="get Player 100")
    interpreter = StubInterpreter(
        ready_intent(
            ResearchCapability.NAMED_TARGET_TRANSFER,
            target_player_name="Player 100",
        )
    )
    try:
        gateway = ConversationGateway(
            GeneralResearchAgent(client, clock=lambda: NOW),
            PlayerCatalogueLoader(client),
            interpreter=interpreter,
            clock=lambda: NOW,
        )
        response = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="missing-hit-limit",
                question="Can I get Player 100 within two gameweeks?",
                squad=source.squad,
                selling_prices_tenths=source.selling_prices_tenths,
            )
        )
    finally:
        await client.aclose()

    assert response.status is ConversationResponseStatus.NEEDS_CLARIFICATION
    assert response.research is None
    assert "How many points" in response.assistant_message


@pytest.mark.anyio
async def test_gateway_recovers_explicit_name_and_hit_from_original_question() -> None:
    client = _client()
    source = _request(question="get Player 100")
    interpreter = StubInterpreter(
        clarification_intent(
            ResearchCapability.NAMED_TARGET_TRANSFER,
            missing=("target_player_name", "maximum_points_hit"),
        )
    )
    try:
        gateway = ConversationGateway(
            GeneralResearchAgent(client, clock=lambda: NOW),
            PlayerCatalogueLoader(client),
            interpreter=interpreter,
            clock=lambda: NOW,
        )
        response = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="explicit-values",
                question=(
                    "Can I get Player 100 within two gameweeks with a maximum hit of minus eight?"
                ),
                squad=source.squad,
                selling_prices_tenths=source.selling_prices_tenths,
            )
        )
    finally:
        await client.aclose()

    assert response.status is ConversationResponseStatus.ANSWERED
    assert response.intent.target_player_name == "player 100"
    assert response.intent.horizon_gameweeks == 2
    assert response.intent.maximum_points_hit == 8
    assert response.research is not None


@pytest.mark.anyio
async def test_gateway_exposes_structured_route_selling_price_requests() -> None:
    client = _client()
    source = _request(question="get Player 100")
    try:
        gateway = ConversationGateway(
            GeneralResearchAgent(client, clock=lambda: NOW),
            PlayerCatalogueLoader(client),
            clock=lambda: NOW,
        )
        response = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="route-price-request",
                question=(
                    "Can I get Player 100 within two gameweeks with a maximum hit of minus eight?"
                ),
                squad=source.squad,
            )
        )
        assert response.research is not None
        assert response.research.report.route_report is not None
        requested_ids = response.research.report.route_report.requested_selling_price_player_ids
        request = response.selling_price_requests[0]
        confirmed = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="route-price-request",
                question=(
                    "Can I get Player 100 within two gameweeks with a maximum hit of minus eight?"
                ),
                selling_prices_tenths={request.player_id: request.current_fpl_price_tenths},
            )
        )
    finally:
        await client.aclose()

    assert response.research is not None
    assert response.research.report.route_report is not None
    assert requested_ids
    assert len(response.selling_price_requests) == len(requested_ids)
    assert request.player_id == requested_ids[0]
    assert request.player_name
    assert request.current_fpl_price_tenths > 0
    assert request.reference_price_basis.value == "current_price_upper_bound"
    assert "actual selling price" in request.reason
    assert confirmed.research is not None
    assert confirmed.selling_price_requests == ()


@pytest.mark.anyio
async def test_gateway_exposes_structured_squad_action_price_request() -> None:
    client = _client()
    source = _request(question="get Player 100")
    try:
        gateway = ConversationGateway(
            GeneralResearchAgent(client, clock=lambda: NOW),
            PlayerCatalogueLoader(client),
            clock=lambda: NOW,
        )
        response = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="squad-action-price-request",
                question="Should I roll or make a transfer this week?",
                squad=source.squad,
            )
        )
    finally:
        await client.aclose()

    assert response.research is not None
    squad_report = response.research.report.squad_action_report
    assert squad_report is not None
    assert squad_report.requested_selling_price_for is not None
    assert len(response.selling_price_requests) == 1
    request = response.selling_price_requests[0]
    assert request.player_id == squad_report.requested_selling_price_for.id
    assert request.player_name == squad_report.requested_selling_price_for.web_name
    assert "leading squad action" in request.reason


@pytest.mark.anyio
async def test_gateway_resolves_protected_player_names_from_team_context() -> None:
    client = _client()
    source = _request(question="get Player 100")
    interpreter = StubInterpreter(
        ready_intent(
            ResearchCapability.NAMED_TARGET_TRANSFER,
            target_player_name="Player 100",
            protected_player_names=("Player 1",),
        )
    )
    try:
        gateway = ConversationGateway(
            GeneralResearchAgent(client, clock=lambda: NOW),
            PlayerCatalogueLoader(client),
            interpreter=interpreter,
            clock=lambda: NOW,
        )
        response = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="protected-name",
                question="How do I get Player 100 without selling Player 1?",
                squad=source.squad,
                selling_prices_tenths=source.selling_prices_tenths,
            )
        )
    finally:
        await client.aclose()

    assert response.status is ConversationResponseStatus.ANSWERED
    assert response.research is not None
    nested = response.research.report.named_target_report
    assert nested is not None
    assert [player.id for player in nested.protected_players] == [1]
    assert response.intent.protected_player_names == ("Player 1",)


@pytest.mark.anyio
async def test_gateway_protects_player_named_in_question_without_model_extraction() -> None:
    client = _client()
    source = _request(question="get Player 100")
    interpreter = StubInterpreter(
        ready_intent(
            ResearchCapability.NAMED_TARGET_TRANSFER,
            target_player_name="Player 100",
        )
    )
    try:
        gateway = ConversationGateway(
            GeneralResearchAgent(client, clock=lambda: NOW),
            PlayerCatalogueLoader(client),
            interpreter=interpreter,
            clock=lambda: NOW,
        )
        response = await gateway.handle(
            ConversationTurnRequest(
                conversation_id="protected-question",
                question="How do I get Player 100 while keeping Player 1?",
                squad=source.squad,
                selling_prices_tenths=source.selling_prices_tenths,
            )
        )
    finally:
        await client.aclose()

    assert response.research is not None
    nested = response.research.report.named_target_report
    assert nested is not None
    assert [player.id for player in nested.protected_players] == [1]


@pytest.mark.anyio
async def test_conversation_endpoint_returns_intent_and_research_response() -> None:
    client = _client()
    source = _request(question="get Player 100")
    interpreter = StubInterpreter(ready_intent(ResearchCapability.HOLD_OR_TRANSFER))
    gateway = ConversationGateway(
        GeneralResearchAgent(client, clock=lambda: NOW),
        PlayerCatalogueLoader(client),
        interpreter=interpreter,
        clock=lambda: NOW,
    )
    app.dependency_overrides[get_conversation_gateway] = lambda: gateway
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            response = await http_client.post(
                "/v1/agent/conversation",
                json={
                    "conversation_id": "endpoint-test",
                    "question": "Should I roll or transfer?",
                    "squad": source.squad.model_dump(mode="json"),
                    "selling_prices_tenths": source.selling_prices_tenths,
                },
            )
    finally:
        app.dependency_overrides.clear()
        await client.aclose()

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "endpoint-test"
    assert body["intent"]["capability"] == "hold_or_transfer"
    assert body["status"] == "answered"
    assert body["research"]["report"]["capability"] == "hold_or_transfer"
    assert body["selling_price_requests"] == []


@pytest.mark.anyio
async def test_conversation_endpoint_returns_structured_selling_price_requests() -> None:
    client = _client()
    source = _request(question="get Player 100")
    gateway = ConversationGateway(
        GeneralResearchAgent(client, clock=lambda: NOW),
        PlayerCatalogueLoader(client),
        clock=lambda: NOW,
    )
    app.dependency_overrides[get_conversation_gateway] = lambda: gateway
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            response = await http_client.post(
                "/v1/agent/conversation",
                json={
                    "conversation_id": "endpoint-price-request",
                    "question": (
                        "Can I get Player 100 within two gameweeks with a maximum hit of "
                        "minus eight?"
                    ),
                    "squad": source.squad.model_dump(mode="json"),
                },
            )
    finally:
        app.dependency_overrides.clear()
        await client.aclose()

    assert response.status_code == 200
    body = response.json()
    assert len(body["selling_price_requests"]) == 1
    request = body["selling_price_requests"][0]
    assert request["player_id"] > 0
    assert request["player_name"]
    assert request["current_fpl_price_tenths"] > 0
    assert request["reference_price_basis"] == "current_price_upper_bound"
    assert "actual selling price" in request["reason"]


def test_intent_validation_requires_question_for_clarification() -> None:
    with pytest.raises(ValueError, match="clarification intents"):
        ConversationIntent(
            capability=ResearchCapability.HOLD_OR_TRANSFER,
            status=ConversationIntentStatus.NEEDS_CLARIFICATION,
            explanation="Missing information.",
        )
