from datetime import timedelta

import httpx
import pytest
from test_named_transfer_decisions import NOW, history, scenario

from gaffertalk_api.domain.models import Money
from gaffertalk_api.domain.pro_research import (
    ConcernKind,
    ConfidenceLevel,
    RiskPreference,
    SquadActionKind,
)
from gaffertalk_api.domain.transfers import TransferPlanningState
from gaffertalk_api.main import app, get_pro_research_loader
from gaffertalk_api.services.squad_action_decisions import SquadActionDecisionService


def run_report(
    *,
    risk: RiskPreference = RiskPreference.BALANCED,
    histories_complete: bool = True,
    created_offset: timedelta = timedelta(0),
    **options: object,
):
    catalogue, snapshot, fixtures, original_state, _, _, _ = scenario(**options)
    assert original_state.bank is not None and original_state.free_transfers is not None
    state = TransferPlanningState(
        bank=original_state.bank,
        free_transfers=original_state.free_transfers,
        selling_prices={pick.player.id: pick.player.current_price for pick in snapshot.picks},
    )
    service = SquadActionDecisionService()
    ids = service.preview_evidence_ids(
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        risk_preference=risk,
    )
    histories = (
        {player_id: history(catalogue.players[player_id]) for player_id in ids}
        if histories_complete
        else {}
    )
    return service.research(
        squad_name="Test squad",
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        risk_preference=risk,
        histories=histories,
        created_at=NOW + created_offset,
    )


def test_clearly_roll_when_no_action_clears_threshold() -> None:
    report = run_report(target_points=15, target_xgi=0.2, alternative_points=15)

    assert report.recommended_action.action is SquadActionKind.ROLL
    assert report.recommended_action.free_transfers_after == 2
    assert report.compared_actions[1].action is SquadActionKind.TRANSFER


def test_clearly_act_on_best_whole_squad_route() -> None:
    report = run_report(target_points=80, target_xgi=4.0)

    assert report.recommended_action.action is SquadActionKind.TRANSFER
    assert report.recommended_action.incoming is not None
    assert report.recommended_action.incoming.id == 16
    assert report.recommended_action.points_hit == 0
    assert report.recommended_action.free_transfers_used == 1
    assert report.recommended_action.free_transfers_after == 0


def test_injured_starter_is_leading_priority_and_deprioritizes_other_players() -> None:
    report = run_report(include_other_risk=True, target_points=60, target_xgi=2.0)

    assert report.ranked_concerns[0].kind is ConcernKind.AVAILABILITY
    assert report.ranked_concerns[0].player.id == 9
    assert "availability" in report.priority_explanation


def test_clearly_avoid_hit_and_roll() -> None:
    report = run_report(
        free_transfers=0,
        target_points=24,
        target_xgi=0.5,
        alternative_points=20,
    )

    assert report.recommended_action.action is SquadActionKind.ROLL
    assert report.hit_analysis.points_hit == 4
    assert report.hit_analysis.justified is False
    assert report.recommended_action.points_hit == 0


def test_large_upgrade_can_justify_hit() -> None:
    report = run_report(
        free_transfers=0,
        target_points=100,
        target_xgi=5.0,
        alternative_points=30,
    )

    assert report.recommended_action.action is SquadActionKind.TRANSFER
    assert report.recommended_action.points_hit == 4
    assert report.hit_analysis.justified is True


def test_risk_preferences_change_thresholds_but_not_legality() -> None:
    reports = {
        risk: run_report(
            risk=risk,
            target_points=16,
            target_xgi=0.3,
            alternative_points=10,
        )
        for risk in RiskPreference
    }

    assert reports[RiskPreference.SAFE].roll_threshold == 12
    assert reports[RiskPreference.BALANCED].roll_threshold == 8
    assert reports[RiskPreference.AGGRESSIVE].roll_threshold == 5
    assert reports[RiskPreference.SAFE].recommended_action.action is SquadActionKind.ROLL
    assert reports[RiskPreference.BALANCED].recommended_action.action is SquadActionKind.TRANSFER
    assert reports[RiskPreference.AGGRESSIVE].recommended_action.action is SquadActionKind.TRANSFER
    transfer_routes = [
        next(
            action
            for action in report.compared_actions
            if action.action is SquadActionKind.TRANSFER
        )
        for report in reports.values()
    ]
    assert (
        len(
            {
                (route.outgoing.id, route.incoming.id)
                for route in transfer_routes
                if route.outgoing and route.incoming
            }
        )
        == 1
    )


def test_incomplete_or_stale_evidence_is_low_confidence() -> None:
    incomplete = run_report(histories_complete=False, target_points=80, target_xgi=4.0)
    stale = run_report(created_offset=timedelta(minutes=16), target_points=80, target_xgi=4.0)

    assert incomplete.confidence.level is ConfidenceLevel.LOW
    assert stale.confidence.level is ConfidenceLevel.LOW
    assert "incomplete" in incomplete.confidence.reasons[1]
    assert "older" in stale.confidence.reasons[0]


def test_tied_priorities_are_ranked_deterministically() -> None:
    catalogue, snapshot, fixtures, original_state, _, _, _ = scenario(include_other_risk=True)
    second_risk = catalogue.players[10].model_copy(update={"status": "i"})
    players = dict(catalogue.players)
    players[10] = second_risk
    catalogue = catalogue.model_copy(update={"players": players})
    picks = tuple(
        pick.model_copy(update={"player": second_risk}) if pick.player.id == 10 else pick
        for pick in snapshot.picks
    )
    snapshot = snapshot.model_copy(update={"picks": picks})
    assert original_state.bank is not None and original_state.free_transfers is not None
    state = TransferPlanningState(
        bank=original_state.bank,
        free_transfers=original_state.free_transfers,
        selling_prices={pick.player.id: pick.player.current_price for pick in snapshot.picks},
    )
    service = SquadActionDecisionService()
    report = service.research(
        squad_name="Tie squad",
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        risk_preference=RiskPreference.BALANCED,
        histories={},
        created_at=NOW,
    )

    assert [concern.player.id for concern in report.ranked_concerns[:2]] == [9, 10]


def test_missing_or_impossible_selling_prices_are_actionable() -> None:
    catalogue, snapshot, fixtures, original_state, _, _, _ = scenario()
    assert original_state.bank is not None and original_state.free_transfers is not None
    missing = TransferPlanningState(
        bank=original_state.bank,
        free_transfers=original_state.free_transfers,
        selling_prices={},
    )
    service = SquadActionDecisionService()

    try:
        service.preview_evidence_ids(
            snapshot=snapshot,
            catalogue=catalogue,
            fixtures=fixtures,
            state=missing,
            risk_preference=RiskPreference.BALANCED,
        )
    except ValueError as error:
        assert "every player" in str(error)
    else:
        raise AssertionError("missing selling prices must fail")

    impossible = TransferPlanningState(
        bank=original_state.bank,
        free_transfers=original_state.free_transfers,
        selling_prices={
            pick.player.id: Money(tenths=pick.player.current_price.tenths + 1)
            for pick in snapshot.picks
        },
    )
    try:
        service.preview_evidence_ids(
            snapshot=snapshot,
            catalogue=catalogue,
            fixtures=fixtures,
            state=impossible,
            risk_preference=RiskPreference.BALANCED,
        )
    except ValueError as error:
        assert "exceeds" in str(error)
    else:
        raise AssertionError("impossible selling prices must fail")


class StubSquadActionLoader:
    async def squad_action(self, request):
        return run_report(risk=request.risk_preference, target_points=80, target_xgi=4.0)


class StubSquadActionGroq:
    model = "test-pro-model"

    async def synthesize_squad_action_report(self, question: str, report):
        return f"Grounded: {report.recommended_action.explanation}"


class FailingSquadActionGroq(StubSquadActionGroq):
    async def synthesize_squad_action_report(self, question: str, report):
        request = httpx.Request("POST", "https://groq.test/chat/completions")
        raise httpx.ConnectError("unavailable", request=request)


def squad_action_payload() -> dict[str, object]:
    return {
        "squad": {
            "name": "Golden squad",
            "player_ids": list(range(1, 16)),
            "bank_tenths": 10,
            "free_transfers": 1,
        },
        "selling_prices_tenths": {str(player_id): 50 for player_id in range(1, 16)},
        "risk_preference": "balanced",
        "question": "What should I do with my transfer this week?",
    }


@pytest.mark.anyio
async def test_squad_action_endpoint_returns_versioned_grounded_report() -> None:
    app.state.groq_client = StubSquadActionGroq()
    app.dependency_overrides[get_pro_research_loader] = lambda: StubSquadActionLoader()
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/pro/research/squad-action",
                json=squad_action_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["schema_version"] == "1.0"
    assert body["report"]["decision_policy_version"] == "1.0"
    assert body["report"]["recommended_action"]["action"] == "transfer"
    assert body["report"]["risk_preference"] == "balanced"
    assert body["assistant_message"].startswith("Grounded:")


@pytest.mark.anyio
async def test_squad_action_provider_failure_has_no_partial_fallback() -> None:
    app.state.groq_client = FailingSquadActionGroq()
    app.dependency_overrides[get_pro_research_loader] = lambda: StubSquadActionLoader()
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/pro/research/squad-action",
                json=squad_action_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "pro_research_unavailable"
    assert "report" not in response.json()


@pytest.mark.anyio
async def test_squad_action_request_requires_every_selling_price() -> None:
    payload = squad_action_payload()
    payload["selling_prices_tenths"] = {"1": 50}
    app.state.groq_client = StubSquadActionGroq()
    app.dependency_overrides[get_pro_research_loader] = lambda: StubSquadActionLoader()
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/pro/research/squad-action", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
