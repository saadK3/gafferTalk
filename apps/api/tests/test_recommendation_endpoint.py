from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from gaffertalk_api.domain.conversation import TransferIntent
from gaffertalk_api.domain.models import (
    Club,
    FplCatalogue,
    GameRules,
    Gameweek,
    Money,
    Player,
    Position,
)
from gaffertalk_api.domain.recommendation_requests import TransferRecommendationRequest
from gaffertalk_api.domain.recommendations import (
    STRATEGY_WEIGHTS,
    RecommendationResult,
    RecommendationStrategy,
)
from gaffertalk_api.main import (
    app,
    get_free_usage,
    get_player_catalogue,
    get_recommendation_loader,
)
from gaffertalk_api.services.free_question_usage import FreeQuestionUsageStore


class StubRecommendationLoader:
    async def recommend(self, request: TransferRecommendationRequest) -> RecommendationResult:
        player = Player(
            id=request.outgoing_player_id,
            web_name="Yates",
            club=Club(id=1, name="Forest", short_name="NFO"),
            position=Position.MIDFIELDER,
            current_price=Money(tenths=45),
            status="a",
        )
        return RecommendationResult(
            squad_name=request.squad.name,
            data_retrieved_at=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
            outgoing=player,
            strategy=request.strategy,
            score_weights=STRATEGY_WEIGHTS[request.strategy],
            recommendations=(),
            assumptions=("Test contract",),
        )


class StubCatalogueLoader:
    async def load(self) -> FplCatalogue:
        positions = (
            [Position.GOALKEEPER] * 2
            + [Position.DEFENDER] * 5
            + [Position.MIDFIELDER] * 5
            + [Position.FORWARD] * 3
        )
        players = {
            player_id: Player(
                id=player_id,
                web_name="Haaland" if player_id == 13 else f"Player {player_id}",
                club=Club(id=player_id, name=f"Club {player_id}", short_name=f"C{player_id}"),
                position=positions[player_id - 1],
                current_price=Money(tenths=50),
                status="a",
            )
            for player_id in range(1, 16)
        }
        players[16] = Player(
            id=16,
            web_name="Isak",
            club=Club(id=16, name="Club 16", short_name="C16"),
            position=Position.FORWARD,
            current_price=Money(tenths=90),
            status="a",
        )
        players[17] = Player(
            id=17,
            web_name="Saka",
            club=Club(id=17, name="Club 17", short_name="C17"),
            position=Position.MIDFIELDER,
            current_price=Money(tenths=50),
            status="a",
        )
        active = Gameweek(
            id=1,
            name="Gameweek 1",
            deadline_time=datetime(2026, 8, 21, 17, 30, tzinfo=UTC),
            finished=False,
            data_checked=False,
            is_previous=False,
            is_current=True,
            is_next=False,
        )
        return FplCatalogue(
            players=players,
            clubs={player.club.id: player.club for player in players.values()},
            gameweeks=(active,),
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
            retrieved_at=datetime.now(UTC),
        )


class StubGroqClient:
    model = "test-model"

    def __init__(self) -> None:
        self.interpret_calls = 0

    async def interpret(
        self, question: str, squad: tuple[Player, ...], selected_outgoing_id: int
    ) -> TransferIntent:
        self.interpret_calls += 1
        return TransferIntent(
            outgoing_player_id=selected_outgoing_id,
            strategy=RecommendationStrategy.BALANCED,
            interpretation=question,
        )

    async def explain(self, question: str, result: RecommendationResult) -> str:
        return f"Grounded answer for: {question}"


class FailingGroqClient(StubGroqClient):
    async def explain(self, question: str, result: RecommendationResult) -> str:
        request = httpx.Request("POST", "https://groq.test/chat/completions")
        raise httpx.ConnectError("Groq unavailable", request=request)


@pytest.mark.anyio
async def test_transfer_recommendation_endpoint_contract() -> None:
    app.dependency_overrides[get_recommendation_loader] = lambda: StubRecommendationLoader()
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/recommendations/transfers",
                json={
                    "squad": {
                        "name": "Test squad",
                        "player_ids": list(range(1, 16)),
                        "bank_tenths": 10,
                        "free_transfers": 1,
                    },
                    "outgoing_player_id": 8,
                    "outgoing_selling_price_tenths": 45,
                    "strategy": "fixture_first",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["squad_name"] == "Test squad"
    assert response.json()["outgoing"]["id"] == 8
    assert response.json()["strategy"] == RecommendationStrategy.FIXTURE_FIRST
    assert response.json()["score_weights"]["upcoming_fixtures"] == 0.6
    assert response.json()["data_retrieved_at"] == "2026-08-22T12:00:00Z"


@pytest.mark.anyio
async def test_conversation_reports_missing_groq_configuration() -> None:
    app.state.groq_client = None
    app.state.recommendation_loader = SimpleNamespace()
    app.state.player_catalogue = SimpleNamespace()
    app.state.free_usage = SimpleNamespace()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/recommendations/conversation",
            headers={"X-GafferTalk-Client-ID": "00000000-0000-4000-8000-000000000001"},
            json={
                "squad": {
                    "name": "Test squad",
                    "player_ids": list(range(1, 16)),
                    "bank_tenths": 10,
                    "free_transfers": 1,
                },
                "outgoing_player_id": 8,
                "outgoing_selling_price_tenths": 45,
                "question": "Who should replace this midfielder?",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "conversation_unconfigured"


@pytest.mark.anyio
async def test_auto_route_is_deterministic_and_does_not_consume_allowance(tmp_path) -> None:
    usage = FreeQuestionUsageStore(tmp_path / "usage.sqlite3")
    app.state.groq_client = None
    app.dependency_overrides[get_player_catalogue] = lambda: StubCatalogueLoader()
    app.dependency_overrides[get_free_usage] = lambda: usage
    transport = httpx.ASGITransport(app=app)
    headers = {"X-GafferTalk-Client-ID": "00000000-0000-4000-8000-000000000001"}
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/recommendations/conversation",
                headers=headers,
                json={
                    "squad": {
                        "name": "Test squad",
                        "player_ids": list(range(1, 16)),
                        "bank_tenths": 10,
                        "free_transfers": 1,
                    },
                    "selection_mode": "auto",
                    "question": "What is the best way to get Saka into my squad?",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["outcome"] == "selling_price_required"
    assert response.json()["suggested_outgoing"]["position"] == "MID"
    assert response.json()["quota"]["remaining"] == 3
    assert response.json()["provider"] == "deterministic"


@pytest.mark.anyio
async def test_free_conversation_enforces_three_successful_questions_per_gameweek(
    tmp_path,
) -> None:
    usage = FreeQuestionUsageStore(tmp_path / "usage.sqlite3")
    app.state.groq_client = StubGroqClient()
    app.dependency_overrides[get_recommendation_loader] = lambda: StubRecommendationLoader()
    app.dependency_overrides[get_player_catalogue] = lambda: StubCatalogueLoader()
    app.dependency_overrides[get_free_usage] = lambda: usage
    transport = httpx.ASGITransport(app=app)
    headers = {"X-GafferTalk-Client-ID": "00000000-0000-4000-8000-000000000001"}
    payload = {
        "squad": {
            "name": "Test squad",
            "player_ids": list(range(1, 16)),
            "bank_tenths": 10,
            "free_transfers": 1,
        },
        "outgoing_player_id": 8,
        "outgoing_selling_price_tenths": 45,
        "question": "Who should replace this midfielder?",
    }
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = [
                await client.post("/v1/recommendations/conversation", json=payload, headers=headers)
                for _ in range(4)
            ]
            usage_response = await client.get("/v1/free/usage", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert [response.status_code for response in responses] == [200, 200, 200, 429]
    assert [response.json()["quota"]["remaining"] for response in responses[:3]] == [2, 1, 0]
    assert responses[3].json()["detail"]["code"] == "free_question_limit_reached"
    assert usage_response.json()["remaining"] == 0


@pytest.mark.anyio
async def test_provider_failure_does_not_consume_a_free_question(tmp_path) -> None:
    usage = FreeQuestionUsageStore(tmp_path / "usage.sqlite3")
    app.state.groq_client = FailingGroqClient()
    app.dependency_overrides[get_recommendation_loader] = lambda: StubRecommendationLoader()
    app.dependency_overrides[get_player_catalogue] = lambda: StubCatalogueLoader()
    app.dependency_overrides[get_free_usage] = lambda: usage
    transport = httpx.ASGITransport(app=app)
    headers = {"X-GafferTalk-Client-ID": "00000000-0000-4000-8000-000000000001"}
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/recommendations/conversation",
                headers=headers,
                json={
                    "squad": {
                        "name": "Test squad",
                        "player_ids": list(range(1, 16)),
                        "bank_tenths": 10,
                        "free_transfers": 1,
                    },
                    "outgoing_player_id": 8,
                    "outgoing_selling_price_tenths": 45,
                    "question": "Who should replace this midfielder?",
                },
            )
            usage_response = await client.get("/v1/free/usage", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "conversation_unavailable"
    assert usage_response.json()["remaining"] == 3


@pytest.mark.anyio
async def test_owned_named_target_skips_groq_and_does_not_consume_allowance(tmp_path) -> None:
    usage = FreeQuestionUsageStore(tmp_path / "usage.sqlite3")
    groq = StubGroqClient()
    app.state.groq_client = groq
    app.dependency_overrides[get_recommendation_loader] = lambda: StubRecommendationLoader()
    app.dependency_overrides[get_player_catalogue] = lambda: StubCatalogueLoader()
    app.dependency_overrides[get_free_usage] = lambda: usage
    transport = httpx.ASGITransport(app=app)
    headers = {"X-GafferTalk-Client-ID": "00000000-0000-4000-8000-000000000001"}
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/recommendations/conversation",
                headers=headers,
                json={
                    "squad": {
                        "name": "Test squad",
                        "player_ids": list(range(1, 16)),
                        "bank_tenths": 10,
                        "free_transfers": 1,
                    },
                    "outgoing_player_id": 8,
                    "outgoing_selling_price_tenths": 45,
                    "question": "How can I get Halaand into my team?",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["outcome"] == "already_owned"
    assert response.json()["quota"]["remaining"] == 3
    assert groq.interpret_calls == 0
