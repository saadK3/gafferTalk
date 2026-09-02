from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from test_named_transfer_decisions import run_report
from test_pro_workspace import confirmed_state

from gaffertalk_api.domain.pro_plans import (
    PlanActionKind,
    PlanEvidenceContext,
    PlanLifecycle,
    PlanLifecycleUpdate,
    PlanReconciliationInput,
    PlanStaleReason,
)
from gaffertalk_api.domain.pro_research import NamedTransferResearchResponse
from gaffertalk_api.domain.pro_workspace import ConfirmedPlanningStateInput
from gaffertalk_api.services.pro_plan_service import ProPlanService
from gaffertalk_api.services.pro_workspace import (
    ProWorkspaceStore,
    WorkspaceStateStaleError,
)

ACCOUNT_A = UUID("11111111-1111-4111-8111-111111111111")
ACCOUNT_B = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 8, 27, 10, 0, tzinfo=UTC)


def evidence_context(
    *,
    snapshot_gameweek: int = 2,
    public_player_ids: tuple[int, ...] = tuple(range(1, 16)),
    fixture_signature: str = "a" * 64,
    player_statuses: dict[int, str] | None = None,
) -> PlanEvidenceContext:
    return PlanEvidenceContext(
        retrieved_at=NOW,
        horizon_gameweeks=(3, 4, 5),
        evidence_gameweeks=(3, 4, 5, 6, 7),
        deadlines={gameweek: NOW + timedelta(days=7 * (gameweek - 2)) for gameweek in range(3, 8)},
        fixture_signature=fixture_signature,
        player_statuses=player_statuses or {player_id: "a" for player_id in range(1, 1000)},
        player_chances={player_id: None for player_id in range(1, 1000)},
        public_snapshot_gameweek=snapshot_gameweek,
        public_player_ids=public_player_ids,
    )


def saved_report_context(store: ProWorkspaceStore):
    workspace = store.save_confirmed_state(
        ACCOUNT_A,
        ConfirmedPlanningStateInput.model_validate(confirmed_state()),
    )
    assert workspace.current_state is not None
    report, *_ = run_report()
    response = NamedTransferResearchResponse(
        report=report,
        assistant_message="Grounded plan source",
        provider="groq",
        model="test-model",
    )
    workspace = store.save_named_transfer_report(
        ACCOUNT_A,
        workspace.current_state.id,
        "Should I make this transfer?",
        response,
    )
    return workspace.reports[0], workspace.current_state


def test_plan_uses_five_gameweeks_for_a_bounded_conditional_three_gameweek_horizon() -> None:
    store = ProWorkspaceStore.in_memory()
    try:
        report, state = saved_report_context(store)
        draft = ProPlanService().build(report, state, evidence_context())

        assert draft.horizon_gameweeks == (3, 4, 5)
        assert draft.evidence_gameweeks == (3, 4, 5, 6, 7)
        assert len([action for action in draft.actions if action.outgoing is not None]) <= 3
        assert (
            len(
                [
                    action
                    for action in draft.actions
                    if action.outgoing is not None and action.gameweek_id == 3
                ]
            )
            <= 2
        )
        assert all(
            action.kind in {PlanActionKind.PLAN, PlanActionKind.WATCH, PlanActionKind.ALTERNATIVE}
            for action in draft.actions
            if action.gameweek_id > 3
        )
        assert draft.conditions
        assert draft.assumptions
        assert draft.confidence == report.report.confidence.level
    finally:
        store.close()


@pytest.mark.parametrize(
    ("context", "private", "checked_at", "expected"),
    [
        (
            evidence_context(snapshot_gameweek=3),
            PlanReconciliationInput(
                bank_tenths=10, free_transfers=1, relevant_selling_price_tenths=50
            ),
            NOW,
            PlanStaleReason.NEW_SNAPSHOT,
        ),
        (
            evidence_context(public_player_ids=tuple(range(2, 17))),
            PlanReconciliationInput(
                bank_tenths=10, free_transfers=1, relevant_selling_price_tenths=50
            ),
            NOW,
            PlanStaleReason.OUTSIDE_TRANSFER,
        ),
        (
            evidence_context(fixture_signature="b" * 64),
            PlanReconciliationInput(
                bank_tenths=10, free_transfers=1, relevant_selling_price_tenths=50
            ),
            NOW,
            PlanStaleReason.FIXTURE_SCHEDULE_CHANGED,
        ),
        (
            evidence_context(player_statuses={player_id: "i" for player_id in range(1, 1000)}),
            PlanReconciliationInput(
                bank_tenths=10, free_transfers=1, relevant_selling_price_tenths=50
            ),
            NOW,
            PlanStaleReason.PLAYER_UNAVAILABLE,
        ),
        (
            evidence_context(),
            PlanReconciliationInput(
                bank_tenths=20, free_transfers=1, relevant_selling_price_tenths=50
            ),
            NOW,
            PlanStaleReason.BANK_CHANGED,
        ),
        (
            evidence_context(),
            PlanReconciliationInput(
                bank_tenths=10, free_transfers=2, relevant_selling_price_tenths=50
            ),
            NOW,
            PlanStaleReason.FREE_TRANSFERS_CHANGED,
        ),
        (
            evidence_context(),
            PlanReconciliationInput(
                bank_tenths=10, free_transfers=1, relevant_selling_price_tenths=51
            ),
            NOW,
            PlanStaleReason.SELLING_PRICE_CHANGED,
        ),
        (
            evidence_context(),
            PlanReconciliationInput(
                bank_tenths=10, free_transfers=1, relevant_selling_price_tenths=50
            ),
            NOW + timedelta(days=8),
            PlanStaleReason.DEADLINE_PASSED,
        ),
    ],
)
def test_defined_staleness_events_are_deterministic(
    context: PlanEvidenceContext,
    private: PlanReconciliationInput,
    checked_at: datetime,
    expected: PlanStaleReason,
) -> None:
    store = ProWorkspaceStore.in_memory()
    try:
        report, state = saved_report_context(store)
        service = ProPlanService()
        draft = service.build(report, state, evidence_context())
        workspace = store.save_plan(ACCOUNT_A, draft)
        plan = workspace.plans[0]
        # The report fixture infers a different selling price; use the plan value unless this case
        # intentionally tests selling-price drift.
        if expected is not PlanStaleReason.SELLING_PRICE_CHANGED:
            private = private.model_copy(
                update={"relevant_selling_price_tenths": plan.relevant_selling_price_tenths}
            )

        result = service.reconcile(plan, state, context, private, checked_at=checked_at)

        assert expected in result.stale_reasons
    finally:
        store.close()


def test_plan_versions_reopen_preserve_history_and_deny_cross_account_access() -> None:
    store = ProWorkspaceStore.in_memory()
    try:
        report, state = saved_report_context(store)
        service = ProPlanService()
        draft = service.build(report, state, evidence_context())
        first = store.save_plan(ACCOUNT_A, draft)
        second = store.save_plan(ACCOUNT_A, draft)

        assert second.plans[0].version == 2
        assert second.plans[0].lifecycle is PlanLifecycle.ACTIVE
        assert second.plans[1].version == 1
        assert second.plans[1].lifecycle is PlanLifecycle.SUPERSEDED
        assert store.get(ACCOUNT_A).plans == second.plans
        with pytest.raises(ValueError, match="does not belong"):
            store.get_plan(ACCOUNT_B, first.plans[0].id)
        with pytest.raises(WorkspaceStateStaleError):
            store.save_plan(ACCOUNT_B, draft)
        reconciliation = service.reconcile(
            second.plans[0],
            state,
            evidence_context(),
            PlanReconciliationInput(
                bank_tenths=state.bank_tenths,
                free_transfers=state.free_transfers,
                relevant_selling_price_tenths=second.plans[0].relevant_selling_price_tenths,
            ),
            checked_at=NOW,
        )
        with pytest.raises(ValueError, match="current active or stale"):
            store.apply_reconciliation(ACCOUNT_B, reconciliation)
        with pytest.raises(ValueError, match="does not belong"):
            store.update_plan_lifecycle(
                ACCOUNT_B,
                second.plans[0].id,
                PlanLifecycleUpdate(lifecycle="abandoned"),
            )
        with pytest.raises(ValueError, match="current active or stale"):
            store.update_plan_lifecycle(
                ACCOUNT_A,
                second.plans[1].id,
                PlanLifecycleUpdate(lifecycle="completed"),
            )
    finally:
        store.close()


def test_material_reconciliation_marks_state_stale_and_blocks_research() -> None:
    store = ProWorkspaceStore.in_memory()
    try:
        report, state = saved_report_context(store)
        service = ProPlanService()
        workspace = store.save_plan(ACCOUNT_A, service.build(report, state, evidence_context()))
        plan = workspace.plans[0]
        reconciliation = service.reconcile(
            plan,
            state,
            evidence_context(snapshot_gameweek=3),
            PlanReconciliationInput(
                bank_tenths=state.bank_tenths,
                free_transfers=state.free_transfers,
                relevant_selling_price_tenths=plan.relevant_selling_price_tenths,
            ),
            checked_at=NOW,
        )

        updated = store.apply_reconciliation(ACCOUNT_A, reconciliation)

        assert updated.plans[0].lifecycle is PlanLifecycle.STALE
        assert updated.current_state is not None
        assert updated.current_state.freshness_status == "stale"
        with pytest.raises(WorkspaceStateStaleError):
            store.current_squad(ACCOUNT_A)
    finally:
        store.close()


def test_new_confirmed_state_stales_active_plan_but_allows_fresh_research() -> None:
    store = ProWorkspaceStore.in_memory()
    try:
        report, state = saved_report_context(store)
        service = ProPlanService()
        store.save_plan(ACCOUNT_A, service.build(report, state, evidence_context()))

        updated = store.save_confirmed_state(
            ACCOUNT_A,
            ConfirmedPlanningStateInput.model_validate(confirmed_state(risk="safe")),
        )

        assert updated.plans[0].lifecycle is PlanLifecycle.STALE
        assert PlanStaleReason.SQUAD_STATE_CHANGED in updated.plans[0].stale_reasons
        assert updated.current_state is not None
        assert updated.current_state.version == 2
        assert updated.current_state.freshness_status == "confirmed"
        store.current_squad(ACCOUNT_A)
    finally:
        store.close()
