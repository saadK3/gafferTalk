from datetime import UTC, datetime

import httpx
import pytest

from gaffertalk_api.domain.models import Club, Money, Player, Position
from gaffertalk_api.main import app


class StubCatalogue:
    async def search(
        self,
        *,
        position: Position,
        query: str,
        limit: int = 30,
    ) -> tuple[Player, ...]:
        assert position is Position.MIDFIELDER
        assert query == "pal"
        assert limit == 30
        return (
            Player(
                id=101,
                web_name="Palmer",
                club=Club(id=1, name="Example Club", short_name="EXC"),
                position=Position.MIDFIELDER,
                current_price=Money(tenths=105),
                status="a",
            ),
        )


@pytest.mark.anyio
async def test_player_endpoint_returns_canonical_search_results() -> None:
    app.state.player_catalogue = StubCatalogue()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/players", params={"position": "MID", "query": "pal"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["players"][0]["web_name"] == "Palmer"
    assert payload["players"][0]["position"] == "MID"
    datetime.fromisoformat(payload["retrieved_at"]).astimezone(UTC)


@pytest.mark.anyio
async def test_player_endpoint_validates_search_inputs() -> None:
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/players", params={"position": "MID", "query": "p"})

    assert response.status_code == 422
