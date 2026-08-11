import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from gaffertalk_api.domain.errors import InvalidTeamIdError
from gaffertalk_api.domain.models import SquadAvailabilityStatus
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.services.team_loader import TeamLoader

FIXTURE_DIRECTORY = Path(__file__).parents[3] / "tests" / "fixtures" / "fpl"
TEAM_ID = 12345


def load_json(name: str) -> Any:
    with (FIXTURE_DIRECTORY / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def bootstrap_with_full_squad() -> dict[str, Any]:
    bootstrap: dict[str, Any] = copy.deepcopy(load_json("bootstrap-static.sample.json"))
    bootstrap["events"].append(
        {
            "id": 2,
            "name": "Gameweek 2",
            "deadline_time": "2026-08-28T17:30:00Z",
            "finished": False,
            "data_checked": False,
            "is_previous": False,
            "is_current": False,
            "is_next": False,
        }
    )
    bootstrap["teams"] = [
        {"id": 101 + index, "name": f"Example FC {index + 1}", "short_name": f"E{index + 1}"}
        for index in range(5)
    ]
    position_types = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]
    bootstrap["elements"] = [
        {
            "id": 1000 + position,
            "web_name": f"Example Player {position}",
            "team": 101 + ((position - 1) % 5),
            "element_type": element_type,
            "now_cost": 45 + position,
            "status": "a",
            "chance_of_playing_next_round": None,
            "news": "",
        }
        for position, element_type in enumerate(position_types, start=1)
    ]
    return bootstrap


def finalized_picks() -> dict[str, Any]:
    return {
        "active_chip": None,
        "automatic_subs": [],
        "entry_history": {
            "event": 1,
            "points": 62,
            "total_points": 62,
            "rank": 100000,
            "overall_rank": 100000,
            "bank": 5,
            "value": 995,
            "event_transfers": 0,
            "event_transfers_cost": 0,
            "points_on_bench": 6,
        },
        "picks": [
            {
                "element": 1000 + position,
                "position": position,
                "multiplier": 2 if position == 8 else 1 if position <= 11 else 0,
                "is_captain": position == 8,
                "is_vice_captain": position == 9,
            }
            for position in range(1, 16)
        ],
    }


def build_handler(*, entry_exists: bool = True) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/bootstrap-static/"):
            return httpx.Response(200, json=bootstrap_with_full_squad())
        if path.endswith(f"/entry/{TEAM_ID}/"):
            if not entry_exists:
                return httpx.Response(404, json={"detail": "No Entry matches the given query."})
            entry = load_json("entry.sample.json")
            entry.update(
                {
                    "current_event": 1,
                    "last_deadline_bank": 5,
                    "last_deadline_value": 995,
                    "summary_overall_points": 62,
                    "summary_overall_rank": 100000,
                }
            )
            return httpx.Response(200, json=entry)
        if path.endswith(f"/entry/{TEAM_ID}/event/1/picks/"):
            return httpx.Response(200, json=finalized_picks())
        return httpx.Response(404, json={"detail": "Not found."})

    return httpx.MockTransport(handler)


async def build_loader(
    now: datetime,
    *,
    entry_exists: bool = True,
) -> tuple[TeamLoader, httpx.AsyncClient]:
    async_client = httpx.AsyncClient(
        base_url="https://example.test/api/",
        transport=build_handler(entry_exists=entry_exists),
    )
    client = FplClient(client=async_client, max_attempts=1)
    return TeamLoader(client, clock=lambda: now), async_client


@pytest.mark.anyio
async def test_valid_preseason_entry_returns_explicit_unavailability() -> None:
    loader, async_client = await build_loader(datetime(2026, 8, 12, tzinfo=UTC))
    try:
        result = await loader.load(TEAM_ID)
    finally:
        await async_client.aclose()

    assert result.entry.id == TEAM_ID
    assert result.entry.team_name == "Example Entry"
    assert result.availability.status is SquadAvailabilityStatus.NOT_YET_PUBLISHED
    assert result.availability.next_deadline == datetime(2026, 8, 21, 17, 30, tzinfo=UTC)
    assert result.snapshot is None


@pytest.mark.anyio
async def test_invalid_team_id_is_not_confused_with_missing_picks() -> None:
    loader, async_client = await build_loader(
        datetime(2026, 8, 12, tzinfo=UTC),
        entry_exists=False,
    )
    try:
        with pytest.raises(InvalidTeamIdError):
            await loader.load(TEAM_ID)
    finally:
        await async_client.aclose()


@pytest.mark.anyio
async def test_finalized_squad_maps_all_picks_and_finances() -> None:
    loader, async_client = await build_loader(datetime(2026, 8, 22, tzinfo=UTC))
    try:
        result = await loader.load(TEAM_ID)
    finally:
        await async_client.aclose()

    assert result.availability.status is SquadAvailabilityStatus.AVAILABLE
    assert result.snapshot is not None
    assert result.snapshot.gameweek.id == 1
    assert len(result.snapshot.picks) == 15
    assert [pick.squad_position for pick in result.snapshot.picks] == list(range(1, 16))
    assert result.snapshot.picks[7].is_captain
    assert result.snapshot.picks[8].is_vice_captain
    assert result.snapshot.bank is not None and result.snapshot.bank.tenths == 5
    assert result.snapshot.squad_value is not None and result.snapshot.squad_value.tenths == 995
