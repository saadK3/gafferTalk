from datetime import datetime

from gaffertalk_api.domain.pro_plans import (
    MATERIAL_STATE_REASONS,
    PlanAction,
    PlanActionKind,
    PlanDraft,
    PlanEvidenceContext,
    PlanEvidenceSummary,
    PlanReconciliation,
    PlanReconciliationInput,
    PlanStaleReason,
    WorkspacePlan,
)
from gaffertalk_api.domain.pro_research import DecisionAction, ProVerdict
from gaffertalk_api.domain.pro_workspace import ConfirmedPlanningState, WorkspaceReport


class ProPlanService:
    """Build and reconcile bounded plans without language-model judgment."""

    def build(
        self,
        report: WorkspaceReport,
        state: ConfirmedPlanningState,
        context: PlanEvidenceContext,
    ) -> PlanDraft:
        if report.squad_state_version != state.version:
            raise ValueError("Run fresh research against the current squad before planning.")
        decision = report.report
        route = decision.requested_route
        expected_selling_price = (
            route.incoming.current_price.tenths + route.remaining_bank.tenths - state.bank_tenths
        )
        expected_selling_price = max(0, expected_selling_price)
        first, second, third = context.horizon_gameweeks
        if decision.verdict is ProVerdict.BUY:
            actions = (
                PlanAction(
                    sequence=1,
                    gameweek_id=first,
                    kind=PlanActionKind.COMMIT_NOW,
                    headline=f"Commit now: {route.outgoing.web_name} → {route.incoming.web_name}",
                    condition=(
                        "Proceed only while both players remain available, the selling price and "
                        "bank match this report, and the deadline has not passed."
                    ),
                    outgoing=route.outgoing,
                    incoming=route.incoming,
                    expected_bank_after_tenths=route.remaining_bank.tenths,
                    expected_free_transfers_after=route.free_transfers_after,
                ),
                PlanAction(
                    sequence=2,
                    gameweek_id=second,
                    kind=PlanActionKind.WATCH,
                    headline=f"Watch {route.incoming.web_name}'s role and availability",
                    condition="Reassess if minutes, status or the scheduled fixture changes.",
                    expected_bank_after_tenths=route.remaining_bank.tenths,
                    expected_free_transfers_after=min(5, route.free_transfers_after + 1),
                ),
                self._alternative_action(
                    sequence=3,
                    gameweek_id=third,
                    report=report,
                    state=state,
                    expected_selling_price=expected_selling_price,
                    fallback_bank=route.remaining_bank.tenths,
                    fallback_free_transfers=min(5, route.free_transfers_after + 2),
                ),
            )
        else:
            actions = (
                PlanAction(
                    sequence=1,
                    gameweek_id=first,
                    kind=PlanActionKind.WATCH,
                    headline=f"Hold {route.outgoing.web_name} for now",
                    condition=(
                        "Do not force the transfer; watch availability, role and the next "
                        "completed "
                        "sample before acting."
                    ),
                    expected_bank_after_tenths=state.bank_tenths,
                    expected_free_transfers_after=state.free_transfers,
                ),
                PlanAction(
                    sequence=2,
                    gameweek_id=second,
                    kind=PlanActionKind.PLAN,
                    headline=(
                        f"Conditionally plan {route.outgoing.web_name} → {route.incoming.web_name}"
                    ),
                    condition=(
                        "Recalculate first; proceed only if the route remains legal, affordable "
                        "and "
                        "the report's change conditions have been met."
                    ),
                    outgoing=route.outgoing,
                    incoming=route.incoming,
                    expected_bank_after_tenths=route.remaining_bank.tenths,
                    expected_free_transfers_after=min(5, state.free_transfers + 1),
                ),
                self._alternative_action(
                    sequence=3,
                    gameweek_id=third,
                    report=report,
                    state=state,
                    expected_selling_price=expected_selling_price,
                    fallback_bank=state.bank_tenths,
                    fallback_free_transfers=min(5, state.free_transfers + 2),
                ),
            )
        evidence = tuple(
            PlanEvidenceSummary(
                player=item.player,
                next_five_difficulties=item.next_five.difficulties,
                next_five_average=item.next_five.average_difficulty,
            )
            for item in decision.evidence
        )
        return PlanDraft(
            report_id=report.id,
            report_version=report.version,
            squad_state_id=state.id,
            squad_state_version=state.version,
            horizon_gameweeks=context.horizon_gameweeks,
            evidence_gameweeks=context.evidence_gameweeks,
            initial_bank_tenths=state.bank_tenths,
            initial_free_transfers=state.free_transfers,
            relevant_selling_price_tenths=expected_selling_price,
            actions=actions,
            conditions=decision.change_conditions,
            alternatives=(
                decision.best_alternative.explanation,
                decision.opportunity_cost.explanation,
            ),
            confidence=decision.confidence.level,
            assumptions=(
                *decision.assumptions,
                "Five-Gameweek evidence informs a conditional three-Gameweek horizon.",
                "Future prices, free transfers and player roles must be recalculated before "
                "acting.",
            ),
            evidence=evidence,
            data_retrieved_at=context.retrieved_at,
            fixture_signature=context.fixture_signature,
            baseline_snapshot_gameweek=context.public_snapshot_gameweek,
            baseline_public_player_ids=context.public_player_ids,
            current_deadline=context.deadlines[context.horizon_gameweeks[0]],
        )

    def reconcile(
        self,
        plan: WorkspacePlan,
        state: ConfirmedPlanningState,
        context: PlanEvidenceContext,
        private_state: PlanReconciliationInput,
        *,
        checked_at: datetime,
    ) -> PlanReconciliation:
        reasons: set[PlanStaleReason] = set()
        baseline = set(plan.baseline_public_player_ids)
        latest = set(context.public_player_ids)
        if context.public_snapshot_gameweek > plan.baseline_snapshot_gameweek:
            reasons.add(PlanStaleReason.NEW_SNAPSHOT)
        if baseline != latest:
            reasons.add(PlanStaleReason.OUTSIDE_TRANSFER)
        if state.id != plan.squad_state_id or state.version != plan.squad_state_version:
            reasons.add(PlanStaleReason.SQUAD_STATE_CHANGED)
        if state.bank_tenths != plan.initial_bank_tenths or (
            private_state.bank_tenths != plan.initial_bank_tenths
        ):
            reasons.add(PlanStaleReason.BANK_CHANGED)
        if state.free_transfers != plan.initial_free_transfers or (
            private_state.free_transfers != plan.initial_free_transfers
        ):
            reasons.add(PlanStaleReason.FREE_TRANSFERS_CHANGED)
        if private_state.relevant_selling_price_tenths != plan.relevant_selling_price_tenths:
            reasons.add(PlanStaleReason.SELLING_PRICE_CHANGED)
        if context.fixture_signature != plan.fixture_signature:
            reasons.add(PlanStaleReason.FIXTURE_SCHEDULE_CHANGED)
        involved_ids = {
            player.id
            for action in plan.actions
            for player in (action.outgoing, action.incoming)
            if player is not None
        }
        if any(
            context.player_statuses.get(player_id, "u") != "a"
            or ((chance := context.player_chances.get(player_id)) is not None and chance < 75)
            for player_id in involved_ids
        ):
            reasons.add(PlanStaleReason.PLAYER_UNAVAILABLE)
        if checked_at >= plan.current_deadline:
            reasons.add(PlanStaleReason.DEADLINE_PASSED)
        ordered = tuple(reason for reason in PlanStaleReason if reason in reasons)
        materially_stale = bool(reasons & MATERIAL_STATE_REASONS)
        return PlanReconciliation(
            plan_id=plan.id,
            checked_at=checked_at,
            newest_snapshot_gameweek=context.public_snapshot_gameweek,
            added_player_ids=tuple(sorted(latest - baseline)),
            removed_player_ids=tuple(sorted(baseline - latest)),
            stale_reasons=ordered,
            materially_stale=materially_stale,
            requires_state_confirmation=materially_stale,
        )

    @staticmethod
    def _alternative_action(
        *,
        sequence: int,
        gameweek_id: int,
        report: WorkspaceReport,
        state: ConfirmedPlanningState,
        expected_selling_price: int,
        fallback_bank: int,
        fallback_free_transfers: int,
    ) -> PlanAction:
        decision = report.report
        alternative = decision.best_alternative
        route = decision.requested_route
        if (
            alternative.action is DecisionAction.ALTERNATIVE_TRANSFER
            and alternative.player is not None
        ):
            bank_after = max(
                0,
                state.bank_tenths
                + expected_selling_price
                - alternative.player.current_price.tenths,
            )
            return PlanAction(
                sequence=sequence,
                gameweek_id=gameweek_id,
                kind=PlanActionKind.ALTERNATIVE,
                headline=(
                    f"Alternative: {route.outgoing.web_name} → {alternative.player.web_name}"
                ),
                condition=(
                    "Use only if it still ranks above the primary route after fresh legality, "
                    "price "
                    "and fixture checks."
                ),
                outgoing=route.outgoing,
                incoming=alternative.player,
                expected_bank_after_tenths=bank_after,
                expected_free_transfers_after=fallback_free_transfers,
            )
        return PlanAction(
            sequence=sequence,
            gameweek_id=gameweek_id,
            kind=PlanActionKind.ALTERNATIVE,
            headline="Alternative: preserve flexibility",
            condition=alternative.explanation,
            expected_bank_after_tenths=fallback_bank,
            expected_free_transfers_after=fallback_free_transfers,
        )
