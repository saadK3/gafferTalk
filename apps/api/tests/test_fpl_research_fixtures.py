import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from gaffertalk_api.integrations.fpl.schemas import FplEntry, FplPicks, FplTransfer

FIXTURE_DIRECTORY = Path(__file__).parents[3] / "tests" / "fixtures" / "fpl"
FORBIDDEN_MANAGER_FIELDS = {
    "player_first_name",
    "player_last_name",
    "player_region_name",
}


def load_fixture(path: Path) -> Any:
    with path.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def test_all_research_fixtures_are_valid_json() -> None:
    fixture_paths = sorted(FIXTURE_DIRECTORY.glob("*.json"))

    assert fixture_paths
    for fixture_path in fixture_paths:
        assert load_fixture(fixture_path) is not None


def test_entry_fixture_excludes_manager_identity() -> None:
    for fixture_name in ("entry.sample.json", "entry-post-deadline.sample.json"):
        entry = load_fixture(FIXTURE_DIRECTORY / fixture_name)

        assert FORBIDDEN_MANAGER_FIELDS.isdisjoint(entry)
        assert entry["name"] == "Example Entry"


def test_money_and_rules_use_observed_integer_units() -> None:
    bootstrap = load_fixture(FIXTURE_DIRECTORY / "bootstrap-static.sample.json")
    settings = bootstrap["game_settings"]
    player = bootstrap["elements"][0]

    assert settings["ui_currency_multiplier"] == 10
    assert settings["squad_total_spend"] == 1000
    assert settings["squad_squadsize"] == 15
    assert settings["squad_team_limit"] == 3
    assert isinstance(player["now_cost"], int)


def test_pre_deadline_picks_are_explicitly_unavailable() -> None:
    response = load_fixture(FIXTURE_DIRECTORY / "picks-unavailable.json")

    assert response == {"detail": "Not found."}


def test_post_deadline_picks_match_the_observed_contract() -> None:
    entry = FplEntry.model_validate(
        load_fixture(FIXTURE_DIRECTORY / "entry-post-deadline.sample.json")
    )
    picks_payload = load_fixture(FIXTURE_DIRECTORY / "picks.sample.json")
    picks = FplPicks.model_validate(picks_payload)

    assert len(picks.picks) == 15
    assert [pick.position for pick in picks.picks] == list(range(1, 16))
    assert sum(pick.is_captain for pick in picks.picks) == 1
    assert sum(pick.is_vice_captain for pick in picks.picks) == 1
    assert entry.last_deadline_bank == picks.entry_history.bank
    assert entry.last_deadline_value == picks.entry_history.value
    assert all("purchase_price" not in pick for pick in picks_payload["picks"])
    assert all("selling_price" not in pick for pick in picks_payload["picks"])


def test_post_deadline_transfers_match_the_observed_contract() -> None:
    payload = load_fixture(FIXTURE_DIRECTORY / "entry-transfers.sample.json")
    transfers = TypeAdapter(list[FplTransfer]).validate_python(payload)

    assert len(transfers) == 1
    assert transfers[0].event == 2
    assert transfers[0].time.isoformat() == "2026-08-28T16:45:00+00:00"
    assert isinstance(payload[0]["element_in_cost"], int)
    assert isinstance(payload[0]["element_out_cost"], int)
