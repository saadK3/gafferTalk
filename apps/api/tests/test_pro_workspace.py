from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from test_named_transfer_decisions import run_report

from gaffertalk_api.domain.pro_research import NamedTransferResearchResponse
from gaffertalk_api.domain.pro_workspace import ConfirmedPlanningStateInput
from gaffertalk_api.domain.recommendation_requests import NamedTransferResearchRequest
from gaffertalk_api.main import app, get_pro_research_loader, get_pro_workspace_store
from gaffertalk_api.services.pro_workspace import (
    ProWorkspaceStore,
    WorkspaceStateRequiredError,
)
from gaffertalk_api.services.supabase_auth import (
    AuthenticatedAccount,
    InvalidAccessTokenError,
)

NOW = datetime(2026, 8, 27, 10, 0, tzinfo=UTC)
ACCOUNT_A = UUID("11111111-1111-4111-8111-111111111111")
ACCOUNT_B = UUID("22222222-2222-4222-8222-222222222222")


def confirmed_state(*, team_id: int = 3906635, risk: str = "balanced") -> dict[str, object]:
    positions = ["GKP"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
    return {
        "team_id": team_id,
        "team_name": f"Team {team_id}",
        "source_gameweek": 2,
        "player_ids": list(range(1, 16)),
        "players": [
            {
                "id": player_id,
                "web_name": f"Player {player_id}",
                "club": {
                    "id": player_id,
                    "name": f"Club {player_id}",
                    "short_name": f"C{player_id}",
                },
                "position": position,
                "current_price": {"tenths": 50},
                "status": "a",
            }
            for player_id, position in enumerate(positions, start=1)
        ],
        "squad_positions": {str(player_id): player_id for player_id in range(1, 16)},
        "changes": [],
        "captain_id": 1,
        "vice_captain_id": 2,
        "bank_tenths": 10,
        "free_transfers": 1,
        "risk_preference": risk,
        "confirmed_at": NOW.isoformat(),
        "data_retrieved_at": NOW.isoformat(),
    }


def test_workspace_versions_state_and_isolates_accounts() -> None:
    store = ProWorkspaceStore.in_memory()
    try:
        first_a = store.save_confirmed_state(
            ACCOUNT_A, ConfirmedPlanningStateInput.model_validate(confirmed_state())
        )
        first_b = store.save_confirmed_state(
            ACCOUNT_B,
            ConfirmedPlanningStateInput.model_validate(confirmed_state(team_id=7654321)),
        )
        second_a = store.save_confirmed_state(
            ACCOUNT_A,
            ConfirmedPlanningStateInput.model_validate(confirmed_state(risk="safe")),
        )

        assert first_a.current_state is not None
        assert first_a.current_state.version == 1
        assert first_b.current_state is not None
        assert first_b.current_state.team_id == 7654321
        assert second_a.current_state is not None
        assert second_a.current_state.version == 2
        assert second_a.current_state.risk_preference.value == "safe"
        assert store.get(ACCOUNT_B).current_state == first_b.current_state
    finally:
        store.close()


def test_visible_messages_and_report_reopen_but_cannot_cross_accounts() -> None:
    store = ProWorkspaceStore.in_memory()
    try:
        workspace_a = store.save_confirmed_state(
            ACCOUNT_A, ConfirmedPlanningStateInput.model_validate(confirmed_state())
        )
        store.save_confirmed_state(
            ACCOUNT_B,
            ConfirmedPlanningStateInput.model_validate(confirmed_state(team_id=7654321)),
        )
        assert workspace_a.current_state is not None
        report, *_ = run_report()
        response = NamedTransferResearchResponse(
            report=report,
            assistant_message="Grounded saved answer",
            provider="groq",
            model="test-model",
        )
        saved = store.save_named_transfer_report(
            ACCOUNT_A,
            workspace_a.current_state.id,
            "Should I make this transfer?",
            response,
        )

        reopened = store.get(ACCOUNT_A)
        assert saved == reopened
        assert [message.role for message in reopened.messages] == ["user", "assistant"]
        assert reopened.reports[0].version == 1
        assert reopened.reports[0].report == report
        assert store.get(ACCOUNT_B).messages == ()
        assert store.get(ACCOUNT_B).reports == ()
        with pytest.raises(WorkspaceStateRequiredError):
            store.save_named_transfer_report(
                ACCOUNT_B,
                workspace_a.current_state.id,
                "Attempt to cross accounts",
                response,
            )
    finally:
        store.close()


class StubAuthVerifier:
    def verify(self, token: str) -> AuthenticatedAccount:
        if token == "account-a":
            return AuthenticatedAccount(id=ACCOUNT_A)
        if token == "account-b":
            return AuthenticatedAccount(id=ACCOUNT_B)
        raise InvalidAccessTokenError("The access token is invalid or expired.")


class StubProResearchLoader:
    async def named_transfer(self, request: NamedTransferResearchRequest):
        report, *_ = run_report()
        return report


class StubProGroq:
    model = "test-pro-model"

    async def synthesize_pro_report(self, question: str, report: object) -> str:
        return "Grounded workspace response"


@pytest.mark.anyio
async def test_authenticated_workspace_journey_persists_and_authorizes_every_read() -> None:
    store = ProWorkspaceStore.in_memory()
    app.state.auth_verifier = StubAuthVerifier()
    app.state.groq_client = StubProGroq()
    app.dependency_overrides[get_pro_workspace_store] = lambda: store
    app.dependency_overrides[get_pro_research_loader] = lambda: StubProResearchLoader()
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            unauthenticated = await client.get("/v1/pro/workspace")
            invalid = await client.get(
                "/v1/pro/workspace", headers={"Authorization": "Bearer invalid"}
            )
            confirmed = await client.put(
                "/v1/pro/workspace/state",
                json=confirmed_state(),
                headers={"Authorization": "Bearer account-a"},
            )
            research = await client.post(
                "/v1/pro/workspace/research/named-transfer",
                json={
                    "outgoing_player_id": 8,
                    "outgoing_selling_price_tenths": 80,
                    "target_player_id": 16,
                    "question": "Should I sell Player 8 for Player 16?",
                },
                headers={"Authorization": "Bearer account-a"},
            )
            reopened = await client.get(
                "/v1/pro/workspace", headers={"Authorization": "Bearer account-a"}
            )
            other_account = await client.get(
                "/v1/pro/workspace", headers={"Authorization": "Bearer account-b"}
            )

        assert unauthenticated.status_code == 401
        assert invalid.status_code == 401
        assert confirmed.status_code == 200
        assert research.status_code == 200
        assert len(reopened.json()["reports"]) == 1
        assert len(reopened.json()["messages"]) == 2
        assert other_account.json()["current_state"] is None
        assert other_account.json()["reports"] == []
    finally:
        app.dependency_overrides.clear()
        store.close()


def test_confirmed_state_rejects_incomplete_squad() -> None:
    invalid = confirmed_state()
    invalid["player_ids"] = list(range(1, 15))
    with pytest.raises(ValueError, match="at least 15 items"):
        ConfirmedPlanningStateInput.model_validate(invalid)
