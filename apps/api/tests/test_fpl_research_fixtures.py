import json
from pathlib import Path
from typing import Any

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
    entry = load_fixture(FIXTURE_DIRECTORY / "entry.sample.json")

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
