from datetime import UTC, datetime, timedelta

from gaffertalk_api.domain.player_evidence import (
    EvidenceAvailability,
    EvidenceFreshness,
    EvidenceNature,
    PlayerEvidenceRequest,
)
from gaffertalk_api.integrations.fpl.client import FplObservation
from gaffertalk_api.integrations.fpl.schemas import (
    FplBootstrap,
    FplElementSummary,
    FplFixture,
)
from gaffertalk_api.services.player_evidence import PlayerEvidenceService

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def bootstrap(*, partial: bool = False) -> FplBootstrap:
    player = {
        "id": 100,
        "web_name": "Haaland",
        "first_name": "Erling",
        "second_name": "Haaland",
        "team": 1,
        "element_type": 4,
        "now_cost": 150,
        "status": "d",
        "total_points": 24,
        "minutes": 270,
        "goals_scored": 4,
        "assists": 1,
        "bonus": 5,
        "selected_by_percent": 52.1,
    }
    if not partial:
        player.update(
            {
                "chance_of_playing_next_round": 75,
                "news": "Knock - 75% chance of playing",
                "news_added": "2026-09-04T16:30:00Z",
                "starts": 3,
                "expected_goals": "2.40",
                "expected_assists": "0.35",
            }
        )
    return FplBootstrap.model_validate(
        {
            "events": [
                {
                    "id": 3,
                    "name": "Gameweek 3",
                    "deadline_time": "2026-09-05T10:00:00Z",
                    "is_current": True,
                }
            ],
            "teams": [
                {"id": 1, "name": "Manchester City", "short_name": "MCI"},
                {"id": 2, "name": "Arsenal", "short_name": "ARS"},
            ],
            "elements": [player],
            "element_types": [
                {
                    "id": 4,
                    "singular_name_short": "FWD",
                    "squad_select": 3,
                    "squad_min_play": 1,
                    "squad_max_play": 3,
                }
            ],
            "game_settings": {
                "squad_squadplay": 11,
                "squad_squadsize": 15,
                "squad_team_limit": 3,
                "squad_total_spend": 1000,
                "ui_currency_multiplier": 10,
                "max_extra_free_transfers": 4,
            },
        }
    )


def summary(*, partial: bool = False, fixture_difficulty: int = 2) -> FplElementSummary:
    history = [
        {
            "round": 1,
            "fixture": 10,
            "opponent_team": 2,
            "was_home": True,
            "kickoff_time": "2026-08-22T14:00:00Z",
            "total_points": 8,
            "minutes": 90,
            "starts": 1,
            "expected_goals": "0.70",
            "expected_assists": "0.00",
        },
        {
            "round": 2,
            "fixture": 20,
            "opponent_team": 2,
            "was_home": False,
            "kickoff_time": "2026-08-29T14:00:00Z",
            "total_points": 2,
            "minutes": 60,
            "starts": 1,
            "expected_goals": "0.10",
            "expected_assists": "0.10",
        },
        {
            "round": 2,
            "fixture": 21,
            "opponent_team": 2,
            "was_home": True,
            "kickoff_time": "2026-09-01T18:00:00Z",
            "total_points": 9,
            "minutes": 90,
            "starts": 1,
            "expected_goals": "0.90",
            "expected_assists": "0.00",
        },
    ]
    if partial:
        history = [{"round": 2, "total_points": 0, "minutes": 0}]
    return FplElementSummary.model_validate(
        {
            "fixtures": [
                {
                    "id": 30,
                    "event": 3,
                    "kickoff_time": "2026-09-12T14:00:00Z",
                    "team_h": 1,
                    "team_a": 2,
                    "is_home": True,
                    "difficulty": fixture_difficulty,
                }
            ],
            "history": history,
            "history_past": [],
        }
    )


def fixture() -> FplFixture:
    return FplFixture.model_validate(
        {
            "id": 30,
            "event": 3,
            "kickoff_time": "2026-09-12T14:00:00Z",
            "team_h": 1,
            "team_a": 2,
            "team_h_difficulty": 2,
            "team_a_difficulty": 4,
        }
    )


def report(
    *,
    partial: bool = False,
    fetched_at: datetime = NOW,
    fixture_difficulty: int = 2,
):
    bootstrap_observation = FplObservation(
        value=bootstrap(partial=partial),
        fetched_at=fetched_at,
        endpoint="bootstrap-static/",
    )
    fixture_observation = FplObservation(
        value=(fixture(),),
        fetched_at=fetched_at,
        endpoint="fixtures/",
    )
    summary_observation = FplObservation(
        value=summary(partial=partial, fixture_difficulty=fixture_difficulty),
        fetched_at=fetched_at,
        endpoint="element-summary/100/",
    )
    return PlayerEvidenceService().build(
        request=PlayerEvidenceRequest(player_ids=(100,), recent_gameweeks=5),
        bootstrap=bootstrap_observation,
        fixtures=fixture_observation,
        summaries={100: summary_observation},
        generated_at=NOW,
    )


def test_complete_report_groups_double_gameweek_and_labels_xg_xa() -> None:
    evidence_report = report()
    player = evidence_report.players[0]

    assert evidence_report.schema_version == "1.0"
    assert evidence_report.freshness is EvidenceFreshness.CURRENT
    assert player.availability is EvidenceAvailability.OBSERVED
    assert player.missing_fields == ()
    assert player.current.news == "Knock - 75% chance of playing"
    assert player.current.source.published_at == datetime(2026, 9, 4, 16, 30, tzinfo=UTC)
    assert player.recent_history is not None
    assert player.recent_history.included_gameweek_ids == (1, 2)
    assert player.recent_history.match_count == 3
    double_gameweek = player.recent_history.gameweeks[1]
    assert double_gameweek.gameweek_id == 2
    assert len(double_gameweek.matches) == 2
    assert double_gameweek.total_points == 11
    assert double_gameweek.total_minutes == 150
    expected = player.recent_history.expected_involvement
    assert expected.expected_goals == 1.7
    assert expected.expected_assists == 0.1
    assert expected.minutes_denominator == 240
    assert expected.nature is EvidenceNature.MODEL_DERIVED
    assert {source.endpoint for source in player.upcoming_fixtures[0].sources} == {
        "fixtures/",
        "element-summary/100/",
    }


def test_partial_report_keeps_observed_zero_and_missing_values_distinct() -> None:
    evidence_report = report(partial=True)
    player = evidence_report.players[0]

    assert player.availability is EvidenceAvailability.PARTIAL
    assert player.season_totals.starts is None
    assert "season_totals.starts" in player.missing_fields
    assert player.recent_history is not None
    match = player.recent_history.gameweeks[0].matches[0]
    assert match.points == 0
    assert match.minutes == 0
    assert match.starts is None
    assert "recent_history.matches.starts" in player.missing_fields


def test_stale_source_time_is_not_replaced_by_report_generation_time() -> None:
    fetched_at = NOW - timedelta(hours=2)
    evidence_report = report(fetched_at=fetched_at)

    assert evidence_report.generated_at == NOW
    assert evidence_report.freshness is EvidenceFreshness.STALE
    assert {source.fetched_at for source in evidence_report.sources} == {fetched_at}


def test_contradictory_fixture_sources_are_exposed() -> None:
    evidence_report = report(fixture_difficulty=5)
    player = evidence_report.players[0]

    assert player.availability is EvidenceAvailability.PARTIAL
    assert len(player.conflicts) == 1
    assert player.conflicts[0].code == "fixture_source_mismatch"
    assert "difficulty" in player.conflicts[0].message


def test_missing_element_summary_produces_useful_partial_evidence() -> None:
    bootstrap_observation = FplObservation(
        value=bootstrap(), fetched_at=NOW, endpoint="bootstrap-static/"
    )
    evidence_report = PlayerEvidenceService().build(
        request=PlayerEvidenceRequest(player_ids=(100,)),
        bootstrap=bootstrap_observation,
        fixtures=FplObservation(value=(fixture(),), fetched_at=NOW, endpoint="fixtures/"),
        summaries={100: None},
        generated_at=NOW,
    )

    player = evidence_report.players[0]
    assert player.availability is EvidenceAvailability.PARTIAL
    assert player.recent_history is None
    assert "recent_history" in player.missing_fields
    assert player.upcoming_fixtures
