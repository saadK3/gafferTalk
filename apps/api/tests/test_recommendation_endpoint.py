from types import SimpleNamespace

import httpx
import pytest

from gaffertalk_api.domain.models import Club, Money, Player, Position
from gaffertalk_api.domain.recommendation_requests import TransferRecommendationRequest
from gaffertalk_api.domain.recommendations import (
    STRATEGY_WEIGHTS,
    RecommendationResult,
    RecommendationStrategy,
)
from gaffertalk_api.main import app, get_recommendation_loader


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
            outgoing=player,
            strategy=request.strategy,
            score_weights=STRATEGY_WEIGHTS[request.strategy],
            recommendations=(),
            assumptions=("Test contract",),
        )


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


@pytest.mark.anyio
async def test_conversation_reports_missing_groq_configuration() -> None:
    app.state.groq_client = None
    app.state.recommendation_loader = SimpleNamespace()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/recommendations/conversation",
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
