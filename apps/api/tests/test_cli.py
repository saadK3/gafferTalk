from datetime import UTC, datetime

from gaffertalk_api.cli import human_output
from gaffertalk_api.domain.models import (
    DataProvenance,
    EntrySummary,
    SquadAvailability,
    SquadAvailabilityStatus,
    SquadLookupResult,
)


def test_human_output_explains_unpublished_squad() -> None:
    result = SquadLookupResult(
        entry=EntrySummary(
            id=12345,
            team_name="Example Entry",
            manager_first_name=None,
            manager_last_name=None,
            current_gameweek_id=None,
            started_gameweek_id=1,
            overall_points=None,
            overall_rank=None,
            last_deadline_bank=None,
            last_deadline_value=None,
            financial_provenance=DataProvenance.UNAVAILABLE,
        ),
        availability=SquadAvailability(
            status=SquadAvailabilityStatus.NOT_YET_PUBLISHED,
            reason="No deadline-finalized squad is publicly available for this entry yet.",
            next_deadline=datetime(2026, 8, 21, 17, 30, tzinfo=UTC),
        ),
        snapshot=None,
        retrieved_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

    output = human_output(result)

    assert "Team ID: 12345" in output
    assert "Team: Example Entry" in output
    assert "Squad status: NOT_YET_PUBLISHED" in output
    assert "21 August 2026, 22:30 PKT" in output
