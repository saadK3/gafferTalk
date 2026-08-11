import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from gaffertalk_api.domain.errors import InvalidUpstreamFplResponseError
from gaffertalk_api.integrations.fpl.client import FplClient

FIXTURE_DIRECTORY = Path(__file__).parents[3] / "tests" / "fixtures" / "fpl"


def load_json(name: str) -> Any:
    with (FIXTURE_DIRECTORY / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


@pytest.mark.anyio
async def test_global_responses_are_validated_and_cached() -> None:
    request_counts = {"bootstrap": 0, "fixtures": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bootstrap-static/"):
            request_counts["bootstrap"] += 1
            return httpx.Response(200, json=load_json("bootstrap-static.sample.json"))
        if request.url.path.endswith("/fixtures/"):
            request_counts["fixtures"] += 1
            return httpx.Response(200, json=load_json("fixtures.sample.json"))
        return httpx.Response(404, json={"detail": "Not found."})

    async_client = httpx.AsyncClient(
        base_url="https://example.test/api/",
        transport=httpx.MockTransport(handler),
    )
    client = FplClient(client=async_client, max_attempts=1)
    try:
        first_bootstrap = await client.get_bootstrap()
        second_bootstrap = await client.get_bootstrap()
        first_fixtures = await client.get_fixtures()
        second_fixtures = await client.get_fixtures()
    finally:
        await async_client.aclose()

    assert first_bootstrap is second_bootstrap
    assert first_fixtures == second_fixtures
    assert request_counts == {"bootstrap": 1, "fixtures": 1}


@pytest.mark.anyio
async def test_invalid_upstream_payload_is_rejected() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"events": []}))
    async_client = httpx.AsyncClient(
        base_url="https://example.test/api/",
        transport=transport,
    )
    client = FplClient(client=async_client, max_attempts=1)
    try:
        with pytest.raises(InvalidUpstreamFplResponseError):
            await client.get_bootstrap()
    finally:
        await async_client.aclose()


@pytest.mark.anyio
async def test_transient_server_failure_is_retried() -> None:
    request_count = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(503, json={"detail": "Temporarily unavailable"})
        return httpx.Response(200, json=load_json("bootstrap-static.sample.json"))

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    async_client = httpx.AsyncClient(
        base_url="https://example.test/api/",
        transport=httpx.MockTransport(handler),
    )
    client = FplClient(client=async_client, max_attempts=2, sleeper=sleeper)
    try:
        bootstrap = await client.get_bootstrap()
    finally:
        await async_client.aclose()

    assert bootstrap.events[0].id == 1
    assert request_count == 2
    assert delays == [0.2]
