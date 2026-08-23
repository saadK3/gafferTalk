import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from gaffertalk_api.domain.models import Position
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.services.player_catalogue import PlayerCatalogueLoader

FIXTURE_DIRECTORY = Path(__file__).parents[3] / "tests" / "fixtures" / "fpl"


def load_json(name: str) -> Any:
    with (FIXTURE_DIRECTORY / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


@pytest.mark.anyio
async def test_catalogue_search_filters_position_and_name() -> None:
    bootstrap: dict[str, Any] = copy.deepcopy(load_json("bootstrap-static.sample.json"))
    bootstrap["elements"].extend(
        [
            {
                "id": 2001,
                "web_name": "Palmer",
                "team": bootstrap["teams"][0]["id"],
                "element_type": 3,
                "now_cost": 105,
                "status": "a",
                "chance_of_playing_next_round": None,
                "news": "",
            },
            {
                "id": 2002,
                "web_name": "Palmer-GK",
                "team": bootstrap["teams"][0]["id"],
                "element_type": 1,
                "now_cost": 50,
                "status": "a",
                "chance_of_playing_next_round": None,
                "news": "",
            },
            {
                "id": 2003,
                "web_name": "Ødegaard",
                "team": bootstrap["teams"][0]["id"],
                "element_type": 3,
                "now_cost": 85,
                "status": "a",
                "chance_of_playing_next_round": None,
                "news": "",
            },
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=bootstrap)

    async_client = httpx.AsyncClient(
        base_url="https://example.test/api/",
        transport=httpx.MockTransport(handler),
    )
    client = FplClient(client=async_client, max_attempts=1)
    loader = PlayerCatalogueLoader(
        client,
        clock=lambda: datetime(2026, 8, 22, tzinfo=UTC),
    )
    try:
        results = await loader.search(position=Position.MIDFIELDER, query="palm")
        normalized_results = await loader.search(
            position=Position.MIDFIELDER,
            query="Odegaard",
        )
    finally:
        await async_client.aclose()

    assert [player.web_name for player in results] == ["Palmer"]
    assert [player.web_name for player in normalized_results] == ["Ødegaard"]
