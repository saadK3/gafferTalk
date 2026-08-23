from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal

from gaffertalk_api.domain.models import (
    DataProvenance,
    Fixture,
    FplCatalogue,
    Player,
    SquadSnapshot,
)
from gaffertalk_api.domain.pro_research import (
    ConfidenceLevel,
    DecisionAction,
    DecisionAlternative,
    DecisionConfidence,
    EvidenceMetric,
    FixtureRun,
    GroundedReason,
    LegalTransferRoute,
    OpportunityCost,
    PlayerEvidence,
    ProDecisionReport,
    ProVerdict,
    SquadPriority,
)
from gaffertalk_api.domain.transfers import (
    ProposedTransfer,
    TransferLegalityResult,
    TransferLegalityStatus,
    TransferPlanningState,
)
from gaffertalk_api.integrations.fpl.schemas import FplElementSummary
from gaffertalk_api.services.transfer_legality import TransferLegalityService


class NamedTransferDecisionService:
    """Compare a requested one-player move with holding, waiting and alternatives."""

    def __init__(self, legality: TransferLegalityService | None = None) -> None:
        self._legality = legality or TransferLegalityService()

    def research(
        self,
        *,
        squad_name: str,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        fixtures: tuple[Fixture, ...],
        state: TransferPlanningState,
        outgoing_player_id: int,
        target_player_id: int,
        histories: dict[int, FplElementSummary],
        created_at: datetime,
    ) -> ProDecisionReport:
        outgoing, target, requested_legality = self._validate_requested(
            snapshot=snapshot,
            catalogue=catalogue,
            state=state,
            outgoing_player_id=outgoing_player_id,
            target_player_id=target_player_id,
        )
        assert requested_legality.remaining_bank is not None
        assert state.free_transfers is not None

        fixture_runs = self._fixture_runs(fixtures)
        outgoing_score = self._score(outgoing, fixture_runs.get(outgoing.club.id))
        target_score = self._score(target, fixture_runs.get(target.club.id))
        candidates = self._legal_alternatives(
            snapshot=snapshot,
            catalogue=catalogue,
            state=state,
            outgoing=outgoing,
            fixture_runs=fixture_runs,
            excluded_id=target.id,
        )
        alternative = candidates[0] if candidates else None
        delta = target_score - outgoing_score
        verdict = self._verdict(delta=delta, points_hit=requested_legality.points_hit)
        squad_priority = self._squad_priority(snapshot, outgoing.id)
        if squad_priority.more_urgent:
            verdict = ProVerdict.WAIT
        elif alternative is not None and alternative[1] >= target_score + 8:
            verdict = ProVerdict.AVOID
        route = LegalTransferRoute(
            outgoing=outgoing,
            incoming=target,
            remaining_bank=requested_legality.remaining_bank,
            free_transfers_after=max(0, state.free_transfers - 1),
            points_hit=requested_legality.points_hit,
        )
        evidence_ids = [outgoing.id, target.id]
        if alternative is not None:
            evidence_ids.append(alternative[0].id)
        evidence = tuple(
            self._player_evidence(
                catalogue.players[player_id],
                fixture_runs.get(catalogue.players[player_id].club.id),
                histories.get(player_id),
                catalogue.retrieved_at,
            )
            for player_id in dict.fromkeys(evidence_ids)
        )
        case_for = self._case_for(target, outgoing, evidence, delta)
        case_against = self._case_against(
            target,
            outgoing,
            evidence,
            delta,
            route,
        )
        best_alternative = self._best_alternative(
            verdict=verdict,
            outgoing=outgoing,
            outgoing_score=outgoing_score,
            alternative=alternative,
        )
        opportunity_cost = self._opportunity_cost(route)
        planning_impact = self._planning_impact(outgoing, target, fixture_runs, route)
        confidence = self._confidence(
            outgoing=outgoing,
            target=target,
            histories=histories,
            separation=abs(delta),
            data_retrieved_at=catalogue.retrieved_at,
            created_at=created_at,
        )
        recommended_action = self._recommended_action(
            verdict,
            outgoing,
            target,
            squad_priority,
            alternative,
            alternative_is_stronger=(
                alternative is not None and alternative[1] >= target_score + 8
            ),
        )
        change_conditions = self._change_conditions(target, outgoing, confidence)
        grounded_reasons = self._grounded_reasons(
            recommended_action=recommended_action,
            case_for=case_for,
            case_against=case_against,
            opportunity_cost=opportunity_cost,
            planning_impact=planning_impact,
            squad_priority=squad_priority,
        )
        return ProDecisionReport(
            squad_name=squad_name,
            created_at=created_at,
            data_retrieved_at=catalogue.retrieved_at,
            verdict=verdict,
            recommended_action=recommended_action,
            compared_actions=(
                DecisionAction.REQUESTED_TRANSFER,
                DecisionAction.HOLD,
                DecisionAction.WAIT,
                *((DecisionAction.ALTERNATIVE_TRANSFER,) if alternative is not None else ()),
            ),
            requested_route=route,
            case_for=case_for,
            case_against=case_against,
            best_alternative=best_alternative,
            squad_priority=squad_priority,
            opportunity_cost=opportunity_cost,
            planning_impact=planning_impact,
            confidence=confidence,
            change_conditions=change_conditions,
            evidence=evidence,
            assumptions=(
                "The squad, bank, free transfers and outgoing selling price are "
                "user-confirmed planning inputs.",
                "Observed player totals come from FPL; per-start, per-90, fixture and "
                "decision scores are deterministic derived metrics.",
                "Five scheduled fixtures inform the comparison; the planning impact "
                "describes only the next three.",
                "This report does not claim live press-conference, tactical-role or "
                "predicted-lineup information.",
            ),
            grounded_reasons=grounded_reasons,
        )

    def preview_evidence_ids(
        self,
        *,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        fixtures: tuple[Fixture, ...],
        state: TransferPlanningState,
        outgoing_player_id: int,
        target_player_id: int,
    ) -> tuple[int, ...]:
        """Return the small validated player set whose per-GW histories are material."""

        outgoing, _, _ = self._validate_requested(
            snapshot=snapshot,
            catalogue=catalogue,
            state=state,
            outgoing_player_id=outgoing_player_id,
            target_player_id=target_player_id,
        )
        fixture_runs = self._fixture_runs(fixtures)
        alternatives = self._legal_alternatives(
            snapshot=snapshot,
            catalogue=catalogue,
            state=state,
            outgoing=outgoing,
            fixture_runs=fixture_runs,
            excluded_id=target_player_id,
        )
        ids = [outgoing_player_id, target_player_id]
        if alternatives:
            ids.append(alternatives[0][0].id)
        return tuple(dict.fromkeys(ids))

    def _validate_requested(
        self,
        *,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        state: TransferPlanningState,
        outgoing_player_id: int,
        target_player_id: int,
    ) -> tuple[Player, Player, TransferLegalityResult]:
        squad_ids = {pick.player.id for pick in snapshot.picks}
        if outgoing_player_id not in squad_ids:
            raise ValueError("the outgoing player must be in the confirmed squad")
        if target_player_id in squad_ids:
            raise ValueError("the target player is already in the confirmed squad")
        try:
            outgoing = catalogue.players[outgoing_player_id]
            target = catalogue.players[target_player_id]
        except KeyError as error:
            raise ValueError(f"unknown current FPL player {error.args[0]}") from error
        if outgoing.position is not target.position:
            raise ValueError("a one-player transfer must preserve the FPL position")
        if target.status != "a":
            raise ValueError("the target player is not currently marked available by FPL")
        legality = self._validate_route(
            snapshot=snapshot,
            catalogue=catalogue,
            state=state,
            outgoing_id=outgoing.id,
            incoming_id=target.id,
        )
        if legality.status is not TransferLegalityStatus.LEGAL:
            reason = legality.rejections[0].detail if legality.rejections else "illegal route"
            raise ValueError(f"the requested transfer is not legal: {reason}")
        return outgoing, target, legality

    def _legal_alternatives(
        self,
        *,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        state: TransferPlanningState,
        outgoing: Player,
        fixture_runs: dict[int, tuple[int, ...]],
        excluded_id: int,
    ) -> list[tuple[Player, float]]:
        squad_ids = {pick.player.id for pick in snapshot.picks}
        candidates: list[tuple[Player, float]] = []
        for candidate in catalogue.players.values():
            if (
                candidate.id in squad_ids
                or candidate.id == excluded_id
                or candidate.position is not outgoing.position
                or candidate.status != "a"
            ):
                continue
            legality = self._validate_route(
                snapshot=snapshot,
                catalogue=catalogue,
                state=state,
                outgoing_id=outgoing.id,
                incoming_id=candidate.id,
            )
            if legality.status is TransferLegalityStatus.LEGAL:
                candidates.append(
                    (candidate, self._score(candidate, fixture_runs.get(candidate.club.id)))
                )
        candidates.sort(key=lambda item: (-item[1], item[0].current_price.tenths, item[0].id))
        return candidates

    def _validate_route(
        self,
        *,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        state: TransferPlanningState,
        outgoing_id: int,
        incoming_id: int,
    ) -> TransferLegalityResult:
        return self._legality.validate(
            snapshot=snapshot,
            catalogue=catalogue,
            state=state,
            transfers=(
                ProposedTransfer(
                    outgoing_player_id=outgoing_id,
                    incoming_player_id=incoming_id,
                ),
            ),
        )

    @staticmethod
    def _fixture_runs(fixtures: tuple[Fixture, ...]) -> dict[int, tuple[int, ...]]:
        by_club: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
        for fixture in fixtures:
            if fixture.started or fixture.finished or fixture.gameweek_id is None:
                continue
            by_club[fixture.home_club_id].append(
                (fixture.gameweek_id, fixture.id, fixture.home_difficulty)
            )
            by_club[fixture.away_club_id].append(
                (fixture.gameweek_id, fixture.id, fixture.away_difficulty)
            )
        return {
            club_id: tuple(item[2] for item in sorted(items)[:5])
            for club_id, items in by_club.items()
        }

    @staticmethod
    def _score(player: Player, difficulties: tuple[int, ...] | None) -> float:
        starts = max(player.starts, 1)
        points_per_start = player.total_points / starts
        xgi_per_90 = (
            (player.expected_goals + player.expected_assists) * 90 / max(player.minutes, 90)
        )
        output_score = min(points_per_start / 8, 1) * 100
        xgi_score = min(xgi_per_90 / 0.8, 1) * 100
        minutes_score = min(player.minutes / (starts * 90), 1) * 100
        average = sum(difficulties) / len(difficulties) if difficulties else 3
        fixture_score = 100 * (6 - average) / 5
        availability_score = (
            100 if player.status == "a" else float(player.chance_of_playing_next_round or 0)
        )
        return round(
            output_score * 0.25
            + xgi_score * 0.25
            + minutes_score * 0.20
            + fixture_score * 0.25
            + availability_score * 0.05,
            1,
        )

    def _player_evidence(
        self,
        player: Player,
        difficulties: tuple[int, ...] | None,
        summary: FplElementSummary | None,
        retrieved_at: datetime,
    ) -> PlayerEvidence:
        recent = tuple(sorted(summary.history, key=lambda item: item.round)[-5:]) if summary else ()
        recent_points = sum(item.total_points for item in recent)
        recent_starts = sum(item.starts for item in recent)
        recent_minutes = sum(item.minutes for item in recent)
        xgi = player.expected_goals + player.expected_assists
        xgi_per_90 = xgi * 90 / max(player.minutes, 90)
        points_per_start = player.total_points / max(player.starts, 1)
        values = difficulties or ()
        next_five = self._fixture_run(values[:5])
        next_three = self._fixture_run(values[:3])
        metrics = (
            self._metric("total_points", "FPL points", player.total_points, "pts", False),
            self._metric("starts", "Starts", player.starts, "", False),
            self._metric("minutes", "Minutes", player.minutes, "min", False),
            self._metric("goals", "Goals", player.goals_scored, "", False),
            self._metric("assists", "Assists", player.assists, "", False),
            self._metric("bonus", "Bonus", player.bonus, "pts", False),
            self._metric(
                "expected_goal_involvement", "Expected goal involvement", xgi, "xGI", False
            ),
            self._metric("points_per_start", "Points per start", points_per_start, "pts", True),
            self._metric("xgi_per_90", "Expected goal involvement per 90", xgi_per_90, "xGI", True),
            self._metric(
                "recent_points",
                "Points in available recent Gameweeks",
                recent_points,
                "pts",
                False,
                source="fpl:element-summary",
                unavailable=summary is None,
            ),
            self._metric(
                "recent_starts",
                "Starts in available recent Gameweeks",
                recent_starts,
                "",
                False,
                source="fpl:element-summary",
                unavailable=summary is None,
            ),
            self._metric(
                "recent_minutes",
                "Minutes in available recent Gameweeks",
                recent_minutes,
                "min",
                False,
                source="fpl:element-summary",
                unavailable=summary is None,
            ),
            self._metric("selected_by", "Selected by", player.selected_by_percent, "%", False),
        )
        return PlayerEvidence(
            player=player,
            metrics=metrics,
            next_five=next_five,
            next_three=next_three,
            recent_gameweeks=tuple(item.round for item in recent),
            evidence_score=self._score(player, values),
            source_retrieved_at=retrieved_at,
        )

    @staticmethod
    def _metric(
        key: str,
        label: str,
        value: float,
        unit: str,
        derived: bool,
        *,
        source: str | None = None,
        unavailable: bool = False,
    ) -> EvidenceMetric:
        rounded = round(float(value), 2)
        display = (
            "Unavailable"
            if unavailable
            else f"{rounded:g}{unit if unit == '%' else f' {unit}' if unit else ''}"
        )
        return EvidenceMetric(
            key=key,
            label=label,
            value=rounded,
            display_value=display,
            provenance=(
                DataProvenance.UNAVAILABLE
                if unavailable
                else DataProvenance.DERIVED
                if derived
                else DataProvenance.OBSERVED
            ),
            source=source or ("derived:gaffertalk-pro-v1" if derived else "fpl:bootstrap-static"),
        )

    @staticmethod
    def _fixture_run(difficulties: tuple[int, ...]) -> FixtureRun:
        average = sum(difficulties) / len(difficulties) if difficulties else None
        return FixtureRun(
            difficulties=difficulties,
            average_difficulty=round(average, 2) if average is not None else None,
            fixtures_considered=len(difficulties),
        )

    @staticmethod
    def _verdict(*, delta: float, points_hit: int) -> ProVerdict:
        adjusted_delta = delta - points_hit * 1.5
        if adjusted_delta >= 8:
            return ProVerdict.BUY
        if adjusted_delta <= -8:
            return ProVerdict.AVOID
        if abs(adjusted_delta) <= 3:
            return ProVerdict.HOLD
        return ProVerdict.WAIT

    @staticmethod
    def _evidence_for(evidence: tuple[PlayerEvidence, ...], player_id: int) -> PlayerEvidence:
        return next(item for item in evidence if item.player.id == player_id)

    def _case_for(
        self,
        target: Player,
        outgoing: Player,
        evidence: tuple[PlayerEvidence, ...],
        delta: float,
    ) -> tuple[str, ...]:
        target_evidence = self._evidence_for(evidence, target.id)
        outgoing_evidence = self._evidence_for(evidence, outgoing.id)
        reasons = [
            f"{target.web_name} is available and the requested route passes every "
            "current one-transfer legality check.",
            f"The evidence model rates {target.web_name} "
            f"{target_evidence.evidence_score:.1f} versus {outgoing.web_name} "
            f"{outgoing_evidence.evidence_score:.1f}.",
        ]
        if target_evidence.next_five.average_difficulty is not None:
            reasons.append(
                f"{target.web_name}'s next-five fixture difficulty averages "
                f"{target_evidence.next_five.average_difficulty:.2f}."
            )
        if delta > 0:
            reasons.append(
                f"The target leads the hold scenario by {delta:.1f} evidence-score points."
            )
        return tuple(reasons)

    def _case_against(
        self,
        target: Player,
        outgoing: Player,
        evidence: tuple[PlayerEvidence, ...],
        delta: float,
        route: LegalTransferRoute,
    ) -> tuple[str, ...]:
        outgoing_evidence = self._evidence_for(evidence, outgoing.id)
        reasons = [
            f"Holding {outgoing.web_name} preserves one transfer; making the move "
            f"would leave £{route.remaining_bank.tenths / 10:.1f}m in the bank.",
            "Waiting one Gameweek preserves the transfer and adds another completed "
            "sample before the same decision is recalculated.",
        ]
        if delta <= 0:
            reasons.append(
                f"The hold scenario leads {target.web_name} by {abs(delta):.1f} "
                "evidence-score points."
            )
        if route.points_hit:
            reasons.append(
                f"The move costs a {route.points_hit}-point hit before any return is earned."
            )
        if min(target.starts, outgoing.starts) < 3:
            reasons.append(
                "The current-season starting sample is too small for a strong form claim."
            )
        if outgoing_evidence.next_five.average_difficulty is not None:
            reasons.append(
                f"Selling gives up {outgoing.web_name}'s next-five fixture run, "
                "currently averaging "
                f"{outgoing_evidence.next_five.average_difficulty:.2f}."
            )
        return tuple(reasons)

    @staticmethod
    def _best_alternative(
        *,
        verdict: ProVerdict,
        outgoing: Player,
        outgoing_score: float,
        alternative: tuple[Player, float] | None,
    ) -> DecisionAlternative:
        if alternative is not None and alternative[1] >= outgoing_score + 8:
            return DecisionAlternative(
                action=DecisionAction.ALTERNATIVE_TRANSFER,
                player=alternative[0],
                explanation=(
                    f"{alternative[0].web_name} is the strongest other legal same-position route "
                    f"in the deterministic evidence ranking ({alternative[1]:.1f})."
                ),
            )
        action = DecisionAction.WAIT if verdict is ProVerdict.WAIT else DecisionAction.HOLD
        explanation = (
            "Wait one Gameweek and reassess the same move with another completed sample."
            if action is DecisionAction.WAIT
            else f"Keep {outgoing.web_name} and preserve the transfer."
        )
        return DecisionAlternative(action=action, explanation=explanation)

    @staticmethod
    def _squad_priority(snapshot: SquadSnapshot, outgoing_id: int) -> SquadPriority:
        risks = [
            pick.player
            for pick in snapshot.picks
            if pick.player.id != outgoing_id and pick.player.status != "a"
        ]
        if not risks:
            return SquadPriority(
                more_urgent=False,
                explanation=(
                    "No other squad player has a stronger FPL availability warning "
                    "in the current data."
                ),
            )
        risks.sort(key=lambda player: (player.chance_of_playing_next_round or 0, player.id))
        player = risks[0]
        return SquadPriority(
            more_urgent=True,
            player=player,
            explanation=(
                f"Review {player.web_name} first: FPL marks the player "
                f"{NamedTransferDecisionService._status_label(player.status)}"
                + (
                    f" with a {player.chance_of_playing_next_round}% chance of playing."
                    if player.chance_of_playing_next_round is not None
                    else "."
                )
            ),
        )

    @staticmethod
    def _status_label(status: str) -> str:
        return {
            "i": "injured",
            "d": "doubtful",
            "s": "suspended",
            "u": "unavailable",
            "n": "unavailable",
        }.get(status, f"flagged ({status})")

    @staticmethod
    def _opportunity_cost(route: LegalTransferRoute) -> OpportunityCost:
        bank = route.remaining_bank.tenths
        flexibility: Literal["strong", "moderate", "limited"] = (
            "strong" if bank >= 15 else "moderate" if bank >= 5 else "limited"
        )
        hit = f" and costs {route.points_hit} points" if route.points_hit else ""
        return OpportunityCost(
            free_transfers_used=1,
            points_hit=route.points_hit,
            remaining_bank=route.remaining_bank,
            flexibility=flexibility,
            explanation=(
                f"The move uses one transfer{hit}, leaves £{bank / 10:.1f}m and "
                f"offers {flexibility} immediate budget flexibility."
            ),
        )

    @staticmethod
    def _planning_impact(
        outgoing: Player,
        target: Player,
        fixture_runs: dict[int, tuple[int, ...]],
        route: LegalTransferRoute,
    ) -> str:
        outgoing_run = fixture_runs.get(outgoing.club.id, ())[:3]
        target_run = fixture_runs.get(target.club.id, ())[:3]
        if outgoing_run and target_run:
            outgoing_average = sum(outgoing_run) / len(outgoing_run)
            target_average = sum(target_run) / len(target_run)
            direction = "easier" if target_average < outgoing_average else "harder"
            return (
                f"Across the next three Gameweeks, {target.web_name}'s fixture average "
                f"is {target_average:.2f} versus {outgoing.web_name}'s "
                f"{outgoing_average:.2f} ({direction}); the route carries "
                f"£{route.remaining_bank.tenths / 10:.1f}m forward."
            )
        return (
            "The next-three fixture comparison is incomplete; preserve flexibility "
            "and recalculate when scheduling data is available."
        )

    @staticmethod
    def _confidence(
        *,
        outgoing: Player,
        target: Player,
        histories: dict[int, FplElementSummary],
        separation: float,
        data_retrieved_at: datetime,
        created_at: datetime,
    ) -> DecisionConfidence:
        complete = outgoing.id in histories and target.id in histories
        sample = min(outgoing.starts, target.starts)
        availability_certain = target.status == "a" and target.chance_of_playing_next_round is None
        data_age = created_at - data_retrieved_at
        fresh = timedelta(0) <= data_age <= timedelta(minutes=15)
        reasons = [
            (
                "FPL catalogue, fixture and availability data were retrieved within "
                "the last 15 minutes."
                if fresh
                else "FPL evidence is older than the 15-minute confidence threshold."
            ),
            f"The deterministic score separation is {separation:.1f} points.",
        ]
        if complete:
            reasons.append("Per-Gameweek history was loaded for both compared players.")
        else:
            reasons.append("Per-Gameweek history is incomplete for at least one compared player.")
        if sample >= 3:
            reasons.append(f"Both players have at least {sample} current-season starts.")
        else:
            unit = "start" if sample == 1 else "starts"
            reasons.append(f"The smaller current-season sample is only {sample} {unit}.")
        if not availability_certain:
            reasons.append("The target has an explicit availability percentage or warning.")
        if fresh and complete and sample >= 5 and separation >= 10 and availability_certain:
            level = ConfidenceLevel.HIGH
        elif fresh and complete and sample >= 3 and separation >= 5:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW
        return DecisionConfidence(level=level, reasons=tuple(reasons))

    @staticmethod
    def _recommended_action(
        verdict: ProVerdict,
        outgoing: Player,
        target: Player,
        squad_priority: SquadPriority,
        alternative: tuple[Player, float] | None,
        alternative_is_stronger: bool,
    ) -> str:
        if squad_priority.more_urgent and squad_priority.player is not None:
            return (
                f"Wait on {outgoing.web_name} to {target.web_name}; review "
                f"{squad_priority.player.web_name} first."
            )
        if alternative is not None and alternative_is_stronger:
            return (
                f"Avoid the requested move for now; {alternative[0].web_name} ranks as "
                "the stronger legal alternative."
            )
        if verdict is ProVerdict.BUY:
            return (
                f"Make the {outgoing.web_name} to {target.web_name} transfer before the deadline."
            )
        if verdict is ProVerdict.HOLD:
            return (
                f"Hold {outgoing.web_name}; the requested move does not offer a clear enough gain."
            )
        if verdict is ProVerdict.WAIT:
            return f"Wait one Gameweek before deciding on {outgoing.web_name} to {target.web_name}."
        return f"Avoid selling {outgoing.web_name} for {target.web_name} on the current evidence."

    @staticmethod
    def _change_conditions(
        target: Player,
        outgoing: Player,
        confidence: DecisionConfidence,
    ) -> tuple[str, ...]:
        conditions = [
            f"A new FPL availability warning for {target.web_name} or {outgoing.web_name}.",
            "A price or confirmed selling-price change that alters route legality or "
            "remaining bank.",
            "A postponement, rescheduling or material change in the next-five fixture run.",
        ]
        if confidence.level is ConfidenceLevel.LOW:
            conditions.append(
                "Another completed Gameweek that materially improves the starts and minutes sample."
            )
        return tuple(conditions)

    @staticmethod
    def _grounded_reasons(
        *,
        recommended_action: str,
        case_for: tuple[str, ...],
        case_against: tuple[str, ...],
        opportunity_cost: OpportunityCost,
        planning_impact: str,
        squad_priority: SquadPriority,
    ) -> tuple[GroundedReason, ...]:
        reasons = [
            GroundedReason(id="recommended_action", text=recommended_action),
            GroundedReason(id="strongest_case_for", text=case_for[0]),
            GroundedReason(id="strongest_case_against", text=case_against[0]),
            GroundedReason(id="opportunity_cost", text=opportunity_cost.explanation),
            GroundedReason(id="planning_impact", text=planning_impact),
        ]
        if squad_priority.more_urgent:
            reasons.append(GroundedReason(id="squad_priority", text=squad_priority.explanation))
        return tuple(reasons)
