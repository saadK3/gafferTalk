from time import perf_counter

import httpx
import pytest
from pydantic import ValidationError
from test_named_transfer_decisions import NOW, history, make_player, scenario

from gaffertalk_api.domain.models import Money, Position
from gaffertalk_api.domain.pro_research import RiskPreference
from gaffertalk_api.domain.recommendation_requests import RouteResearchRequest
from gaffertalk_api.domain.route_research import RouteSearchStatus, RouteVerdict
from gaffertalk_api.domain.transfers import (
    ProposedTransfer,
    TransferLegalityStatus,
    TransferPlanningState,
)
from gaffertalk_api.main import app, get_pro_research_loader
from gaffertalk_api.services.route_research import (
    MAX_SECONDARY_CANDIDATES_PER_POSITION,
    RouteResearchService,
)
from gaffertalk_api.services.transfer_legality import TransferLegalityService


def route_scenario(*, target_price: int = 110, target_points: int = 90):
    catalogue, snapshot, fixtures, original, outgoing, target, _ = scenario(
        target_points=target_points,
        target_xgi=4.0 if target_points > 30 else 0.1,
    )
    target = target.model_copy(update={"current_price": Money(tenths=target_price)})
    enabler = make_player(
        18,
        Position.FORWARD,
        price=30,
        points=25,
        expected_goals=0.4,
        expected_assists=0.4,
    )
    players = {**catalogue.players, target.id: target, enabler.id: enabler}
    clubs = {**catalogue.clubs, enabler.club.id: enabler.club}
    catalogue = catalogue.model_copy(update={"players": players, "clubs": clubs})
    state = TransferPlanningState(
        bank=original.bank,
        free_transfers=original.free_transfers,
        selling_prices={},
    )
    return catalogue, snapshot, fixtures, state, outgoing, target, enabler


def run_route(
    *,
    confirmed_prices: dict[int, int] | None = None,
    preserved: tuple[int, ...] = (),
    excluded: tuple[int, ...] = (),
    minimum_bank: int = 0,
    maximum_transfers: int = 2,
    proceed: bool = False,
    target_price: int = 110,
    target_points: int = 90,
    purchase_prices: dict[int, int] | None = None,
):
    catalogue, snapshot, fixtures, state, outgoing, target, enabler = route_scenario(
        target_price=target_price,
        target_points=target_points,
    )
    state = state.model_copy(
        update={
            "selling_prices": {
                player_id: Money(tenths=price)
                for player_id, price in (confirmed_prices or {}).items()
            }
        }
    )
    service = RouteResearchService()
    ids = service.preview_evidence_ids(
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        target_player_id=target.id,
        preserved_player_ids=preserved,
        excluded_player_ids=excluded,
        minimum_remaining_bank=Money(tenths=minimum_bank),
        maximum_transfers=maximum_transfers,
        risk_preference=RiskPreference.BALANCED,
        purchase_prices={
            player_id: Money(tenths=price) for player_id, price in (purchase_prices or {}).items()
        },
    )
    report = service.research(
        squad_name="Route squad",
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        target_player_id=target.id,
        preserved_player_ids=preserved,
        excluded_player_ids=excluded,
        minimum_remaining_bank=Money(tenths=minimum_bank),
        maximum_transfers=maximum_transfers,
        risk_preference=RiskPreference.BALANCED,
        proceed_if_discouraged=proceed,
        purchase_prices={
            player_id: Money(tenths=price) for player_id, price in (purchase_prices or {}).items()
        },
        histories={player_id: history(catalogue.players[player_id]) for player_id in ids},
        created_at=NOW,
    )
    return report, catalogue, snapshot, state, outgoing, target, enabler


def test_two_transfer_route_requests_only_its_outgoing_prices_then_becomes_exact() -> None:
    preliminary, *_ = run_route()

    assert preliminary.status is RouteSearchStatus.NEEDS_SELLING_PRICES
    assert preliminary.provisional_route is not None
    assert len(preliminary.provisional_route.transfers) == 2
    requested = preliminary.requested_selling_prices_for
    assert {player.id for player in requested} == {
        transfer.outgoing.id for transfer in preliminary.provisional_route.transfers
    }
    assert preliminary.provisional_route.budget_status == "optimistic"
    assert "not yet confirmed affordable or legal" in preliminary.provisional_route.explanation

    final, catalogue, snapshot, _, *_ = run_route(
        confirmed_prices={player.id: player.current_price.tenths for player in requested}
    )
    assert final.status is RouteSearchStatus.ROUTE
    assert final.recommended_route is not None
    assert final.recommended_route.budget_status == "exact"
    assert len(final.recommended_route.transfers) == 2
    assert all(route.budget_status == "exact" for route in final.alternatives)
    exact_state = TransferPlanningState(
        bank=Money(tenths=10),
        free_transfers=1,
        selling_prices={
            transfer.outgoing.id: transfer.confirmed_selling_price
            for transfer in final.recommended_route.transfers
            if transfer.confirmed_selling_price is not None
        },
    )
    legality = TransferLegalityService().validate(
        snapshot=snapshot,
        catalogue=catalogue,
        state=exact_state,
        transfers=tuple(
            ProposedTransfer(
                outgoing_player_id=transfer.outgoing.id,
                incoming_player_id=transfer.incoming.id,
            )
            for transfer in final.recommended_route.transfers
        ),
    )
    assert legality.status is TransferLegalityStatus.LEGAL
    assert legality.remaining_bank == final.recommended_route.remaining_bank
    assert legality.points_hit == final.recommended_route.points_hit == 4


def test_affordable_target_prefers_one_transfer_route() -> None:
    preliminary, *_ = run_route(target_price=85)
    assert preliminary.provisional_route is not None
    assert len(preliminary.provisional_route.transfers) == 1


def test_failed_exact_route_requests_only_the_next_relevant_prices() -> None:
    first, *_ = run_route()
    assert first.provisional_route is not None
    first_ids = {player.id for player in first.requested_selling_prices_for}
    failed_prices = {player_id: 30 for player_id in first_ids}

    next_report, *_ = run_route(confirmed_prices=failed_prices)

    assert next_report.status is RouteSearchStatus.NEEDS_SELLING_PRICES
    assert next_report.requested_selling_prices_for
    assert {player.id for player in next_report.requested_selling_prices_for} - first_ids


def test_preserve_exclude_and_minimum_bank_constraints_shape_route() -> None:
    preliminary, _, _, _, outgoing, _, _ = run_route(
        preserved=(8,),
        excluded=(13,),
        minimum_bank=5,
        target_price=75,
    )
    assert preliminary.provisional_route is not None
    outgoing_ids = {transfer.outgoing.id for transfer in preliminary.provisional_route.transfers}
    assert outgoing.id not in outgoing_ids
    assert 13 in outgoing_ids
    assert preliminary.provisional_route.remaining_bank.tenths >= 5


def test_no_supported_route_is_distinct_from_discouraged_legal_route() -> None:
    no_route, *_ = run_route(maximum_transfers=1, target_price=110)
    assert no_route.status is RouteSearchStatus.NO_LEGAL_ROUTE
    assert no_route.verdict is RouteVerdict.NO_ROUTE

    preliminary, *_ = run_route(target_price=70, target_points=0)
    assert preliminary.provisional_route is not None
    prices = {
        transfer.outgoing.id: transfer.outgoing.current_price.tenths
        for transfer in preliminary.provisional_route.transfers
    }
    discouraged, *_ = run_route(
        confirmed_prices=prices,
        target_price=70,
        target_points=0,
        proceed=True,
    )
    assert discouraged.status is RouteSearchStatus.ROUTE
    assert discouraged.verdict is RouteVerdict.DISCOURAGED
    assert discouraged.manager_override is True
    assert "without changing that verdict" in discouraged.strategic_explanation


def test_purchase_price_cross_check_rejects_inconsistent_selling_price() -> None:
    with pytest.raises(ValueError, match="does not match"):
        run_route(
            confirmed_prices={8: 80},
            purchase_prices={8: 60},
            target_price=85,
        )


def test_contradictory_and_overwide_constraints_are_rejected() -> None:
    payload = route_payload()
    payload["preserved_player_ids"] = [8]
    payload["excluded_player_ids"] = [8]
    with pytest.raises(ValidationError, match="both preserved and excluded"):
        RouteResearchRequest.model_validate(payload)

    with pytest.raises(ValueError, match="at most two owned players"):
        run_route(excluded=(1, 2, 3))


def test_search_is_bounded_deterministic_and_within_latency_budget() -> None:
    started = perf_counter()
    first, *_ = run_route()
    second, *_ = run_route()
    elapsed = perf_counter() - started

    assert first.provisional_route == second.provisional_route
    assert first.search_stats.candidate_limit_per_position == MAX_SECONDARY_CANDIDATES_PER_POSITION
    assert first.search_stats.routes_examined > 0
    assert elapsed < 1.0


class StubRouteLoader:
    async def route(self, request: RouteResearchRequest):
        report, *_ = run_route(confirmed_prices=request.selling_prices_tenths)
        return report


class StubRouteGroq:
    model = "test-route-model"

    async def synthesize_route_report(self, question: str, report):
        return report.grounded_reasons[0].text


class FailingRouteGroq(StubRouteGroq):
    async def synthesize_route_report(self, question: str, report):
        request = httpx.Request("POST", "https://groq.test/chat/completions")
        raise httpx.ConnectError("unavailable", request=request)


def route_payload() -> dict[str, object]:
    return {
        "squad": {
            "name": "Route squad",
            "player_ids": list(range(1, 16)),
            "bank_tenths": 10,
            "free_transfers": 1,
        },
        "target_player_id": 16,
        "preserved_player_ids": [],
        "excluded_player_ids": [],
        "minimum_remaining_bank_tenths": 0,
        "maximum_transfers": 2,
        "selling_prices_tenths": {},
        "risk_preference": "balanced",
        "proceed_if_discouraged": False,
        "question": "How can I get Player 16 in two transfers?",
    }


@pytest.mark.anyio
async def test_route_endpoint_returns_versioned_grounded_report() -> None:
    app.state.groq_client = StubRouteGroq()
    app.dependency_overrides[get_pro_research_loader] = lambda: StubRouteLoader()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/v1/pro/research/route", json=route_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["schema_version"] == "1.0"
    assert body["report"]["status"] == "needs_selling_prices"
    assert len(body["report"]["requested_selling_prices_for"]) == 2
    assert body["assistant_message"]


@pytest.mark.anyio
async def test_route_provider_failure_returns_no_partial_report() -> None:
    app.state.groq_client = FailingRouteGroq()
    app.dependency_overrides[get_pro_research_loader] = lambda: StubRouteLoader()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/v1/pro/research/route", json=route_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "pro_research_unavailable"
    assert "report" not in response.json()
