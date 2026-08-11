from datetime import UTC, datetime

import httpx
import pytest

from gaffertalk_api.domain.errors import InvalidTeamIdError
from gaffertalk_api.domain.models import (
    DataProvenance,
    EntrySummary,
    SquadAvailability,
    SquadAvailabilityStatus,
    SquadLookupResult,
)
from gaffertalk_api.main import app

TEAM_ID = 12345


def unavailable_result() -> SquadLookupResult:
    return SquadLookupResult(
        entry=EntrySummary(
            id=TEAM_ID,
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


class StubLoader:
    def __init__(self, result: SquadLookupResult | None) -> None:
        self._result = result

    async def load(self, team_id: int) -> SquadLookupResult:
        if self._result is None:
            raise InvalidTeamIdError(team_id)
        return self._result


@pytest.mark.anyio
async def test_team_endpoint_returns_canonical_lookup_result() -> None:
    app.state.team_loader = StubLoader(unavailable_result())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/entries/{TEAM_ID}/squad")

    assert response.status_code == 200
    assert response.json()["entry"]["id"] == TEAM_ID
    assert response.json()["availability"]["status"] == "not_yet_published"
    assert response.json()["snapshot"] is None


@pytest.mark.anyio
async def test_team_endpoint_maps_invalid_id_to_structured_404() -> None:
    app.state.team_loader = StubLoader(None)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/entries/{TEAM_ID}/squad")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "invalid_team_id"
