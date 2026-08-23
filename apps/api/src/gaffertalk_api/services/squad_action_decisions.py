from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from gaffertalk_api.domain.models import Fixture, FplCatalogue, Player, SquadSnapshot
from gaffertalk_api.domain.pro_research import (
    ConcernKind,
    ConfidenceLevel,
    GroundedReason,
    HitAnalysis,
    RankedSquadConcern,
    RiskPreference,
    SquadActionCandidate,
    SquadActionConfidence,
    SquadActionKind,
    SquadActionReport,
    SquadActionStatus,
)
from gaffertalk_api.domain.transfers import (
    ProposedTransfer,
    TransferLegalityStatus,
    TransferPlanningState,
)
from gaffertalk_api.integrations.fpl.schemas import FplElementSummary
from gaffertalk_api.services.named_transfer_decisions import NamedTransferDecisionService
from gaffertalk_api.services.transfer_legality import TransferLegalityService


@dataclass(frozen=True)
class Policy:
    roll_threshold: float
    hit_threshold: float
    hit_score_penalty: float


POLICIES = {
    RiskPreference.SAFE: Policy(roll_threshold=12.0, hit_threshold=22.0, hit_score_penalty=2.5),
    RiskPreference.BALANCED: Policy(roll_threshold=8.0, hit_threshold=16.0, hit_score_penalty=2.0),
    RiskPreference.AGGRESSIVE: Policy(
        roll_threshold=5.0, hit_threshold=11.0, hit_score_penalty=1.5
    ),
}


class SquadActionDecisionService:
    """Rank legal one-transfer actions against rolling for the whole squad."""

    def __init__(self, legality: TransferLegalityService | None = None) -> None:
        self._legality = legality or TransferLegalityService()
        self._evidence = NamedTransferDecisionService(self._legality)

    def research(
        self,
        *,
        squad_name: str,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        fixtures: tuple[Fixture, ...],
        state: TransferPlanningState,
        risk_preference: RiskPreference,
        histories: dict[int, FplElementSummary],
        created_at: datetime,
    ) -> SquadActionReport:
        self._validate_state(snapshot, catalogue, state)
        policy = POLICIES[risk_preference]
        fixture_runs = self._evidence._fixture_runs(fixtures)
        scores = {
            player.id: self._evidence._score(player, fixture_runs.get(player.club.id))
            for player in catalogue.players.values()
        }
        optimistic_state = self._optimistic_state(snapshot, catalogue, state)
        concerns, optimistic_actions = self._evaluate(
            snapshot=snapshot,
            catalogue=catalogue,
            state=optimistic_state,
            scores=scores,
            policy=policy,
            budget_status="optimistic",
        )
        roll = self._roll_action(snapshot, state, catalogue)
        qualifying = [action for action in optimistic_actions if self._qualifies(action, policy)]
        status = SquadActionStatus.ROLL
        recommended: SquadActionCandidate | None = roll
        provisional: SquadActionCandidate | None = None
        requested_player: Player | None = None
        material_action = optimistic_actions[0] if optimistic_actions else None
        attempted_confirmation = False
        for optimistic in qualifying:
            assert optimistic.outgoing is not None
            outgoing_id = optimistic.outgoing.id
            if outgoing_id not in state.selling_prices:
                status = SquadActionStatus.NEEDS_SELLING_PRICE
                recommended = None
                provisional = optimistic
                requested_player = optimistic.outgoing
                material_action = optimistic
                break
            attempted_confirmation = True
            exact_state = optimistic_state.model_copy(
                update={
                    "selling_prices": {
                        **optimistic_state.selling_prices,
                        outgoing_id: state.selling_prices[outgoing_id],
                    }
                }
            )
            _, exact_actions = self._evaluate(
                snapshot=snapshot,
                catalogue=catalogue,
                state=exact_state,
                scores=scores,
                policy=policy,
                budget_status="exact",
            )
            exact = next(
                (
                    action
                    for action in exact_actions
                    if action.outgoing is not None and action.outgoing.id == outgoing_id
                ),
                None,
            )
            if exact is not None and self._qualifies(exact, policy):
                status = SquadActionStatus.TRANSFER
                recommended = exact
                material_action = exact
                concerns = self._confirm_selected_concern(concerns, exact)
                break
        else:
            if attempted_confirmation and qualifying:
                status = SquadActionStatus.INSUFFICIENT_GAIN

        lead = recommended or provisional or roll
        compared = tuple(
            [
                lead,
                roll,
                *[item for item in optimistic_actions[:3] if not self._same_route(item, lead)],
            ]
        )
        compared = tuple(dict.fromkeys(compared))
        evidence_ids = self._evidence_ids(concerns, material_action)
        evidence = tuple(
            self._evidence._player_evidence(
                catalogue.players[player_id],
                fixture_runs.get(catalogue.players[player_id].club.id),
                histories.get(player_id),
                catalogue.retrieved_at,
            )
            for player_id in evidence_ids
        )
        confidence = self._confidence(
            evidence_ids=evidence_ids,
            histories=histories,
            catalogue=catalogue,
            created_at=created_at,
            separation=(material_action.policy_adjusted_gain if material_action else 0),
        )
        hit_analysis = self._hit_analysis(material_action, policy)
        priority_explanation = concerns[0].explanation
        if status is SquadActionStatus.NEEDS_SELLING_PRICE and requested_player is not None:
            planning_impact = (
                f"Confirm {requested_player.web_name}'s selling price before the provisional "
                "route can be described as affordable or legal."
            )
            action_reason = (
                f"The squad diagnosis is preliminary. Confirm {requested_player.web_name}'s "
                "selling price to validate the leading route."
            )
        elif status is SquadActionStatus.INSUFFICIENT_GAIN:
            planning_impact = self._planning_impact(roll, state)
            action_reason = (
                "The previously promising route does not clear the selected policy after exact "
                "selling-price validation; roll the transfer."
            )
        else:
            planning_impact = self._planning_impact(lead, state)
            action_reason = lead.explanation
        grounded_reasons = (
            GroundedReason(id="recommended_action", text=action_reason),
            GroundedReason(id="leading_priority", text=priority_explanation),
            GroundedReason(id="roll_comparison", text=self._roll_comparison(lead, policy)),
            GroundedReason(id="hit_analysis", text=hit_analysis.comparison),
            GroundedReason(id="planning_impact", text=planning_impact),
        )
        return SquadActionReport(
            squad_name=squad_name,
            created_at=created_at,
            data_retrieved_at=catalogue.retrieved_at,
            risk_preference=risk_preference,
            status=status,
            recommended_action=recommended,
            provisional_action=provisional,
            requested_selling_price_for=requested_player,
            ranked_concerns=concerns,
            compared_actions=compared,
            roll_threshold=policy.roll_threshold,
            priority_explanation=priority_explanation,
            hit_analysis=hit_analysis,
            planning_impact=planning_impact,
            confidence=confidence,
            change_conditions=(
                "A new FPL availability warning or recovery changes the squad-priority order.",
                "A confirmed selling price, bank or free-transfer change alters route legality.",
                "A fixture change or another completed Gameweek moves an action across the "
                f"{policy.roll_threshold:.0f}-point {risk_preference.value} roll threshold.",
            ),
            evidence=evidence,
            assumptions=(
                "The bank and free-transfer count are manager-confirmed planning inputs.",
                "Unconfirmed selling prices use current FPL price only as an optimistic upper "
                "bound; optimistic routes are never presented as legal or final.",
                "A final transfer uses the manager-confirmed selling price for its outgoing "
                "player and canonical legality validation.",
                "Only normal one-player transfers are evaluated; chips and two-transfer routes "
                "are outside this report.",
                "Evidence scores rank observed FPL output, minutes, availability and fixtures; "
                "they are not expected FPL points.",
                "Safe, Balanced and Aggressive change documented action thresholds and hit "
                "penalties, never transfer legality.",
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
        risk_preference: RiskPreference,
    ) -> tuple[int, ...]:
        self._validate_state(snapshot, catalogue, state)
        fixture_runs = self._evidence._fixture_runs(fixtures)
        scores = {
            player.id: self._evidence._score(player, fixture_runs.get(player.club.id))
            for player in catalogue.players.values()
        }
        optimistic_state = self._optimistic_state(snapshot, catalogue, state)
        concerns, actions = self._evaluate(
            snapshot=snapshot,
            catalogue=catalogue,
            state=optimistic_state,
            scores=scores,
            policy=POLICIES[risk_preference],
            budget_status="optimistic",
        )
        policy = POLICIES[risk_preference]
        action = next((item for item in actions if self._qualifies(item, policy)), None)
        return self._evidence_ids(concerns, action or (actions[0] if actions else None))

    @staticmethod
    def _validate_state(
        snapshot: SquadSnapshot, catalogue: FplCatalogue, state: TransferPlanningState
    ) -> None:
        if state.bank is None:
            raise ValueError("confirm the current bank before whole-squad research")
        if state.free_transfers is None:
            raise ValueError("confirm free transfers before whole-squad research")
        squad_ids = {pick.player.id for pick in snapshot.picks}
        if not set(state.selling_prices).issubset(squad_ids):
            raise ValueError("selling prices may only reference players in the squad")
        for player_id, price in state.selling_prices.items():
            if price.tenths > catalogue.players[player_id].current_price.tenths:
                raise ValueError(
                    f"selling price for {catalogue.players[player_id].web_name} exceeds "
                    "the current FPL price"
                )

    @staticmethod
    def _optimistic_state(
        snapshot: SquadSnapshot, catalogue: FplCatalogue, state: TransferPlanningState
    ) -> TransferPlanningState:
        return state.model_copy(
            update={
                "selling_prices": {
                    pick.player.id: catalogue.players[pick.player.id].current_price
                    for pick in snapshot.picks
                }
            }
        )

    @staticmethod
    def _qualifies(action: SquadActionCandidate, policy: Policy) -> bool:
        threshold = policy.hit_threshold if action.points_hit else policy.roll_threshold
        return action.policy_adjusted_gain >= threshold

    def _evaluate(
        self,
        *,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        state: TransferPlanningState,
        scores: dict[int, float],
        policy: Policy,
        budget_status: Literal["optimistic", "exact"],
    ) -> tuple[tuple[RankedSquadConcern, ...], list[SquadActionCandidate]]:
        squad_ids = {pick.player.id for pick in snapshot.picks}
        bench = tuple(
            pick.player
            for pick in snapshot.picks
            if pick.squad_position > catalogue.rules.starting_size
        )
        concern_rows: list[tuple[float, int, Player, ConcernKind, str]] = []
        actions: list[SquadActionCandidate] = []
        for pick in snapshot.picks:
            player = pick.player
            starting = pick.squad_position <= catalogue.rules.starting_size
            chance = player.chance_of_playing_next_round
            if player.status != "a":
                severity = 100 - (chance if chance is not None else 0)
                has_cover = any(
                    cover.status == "a"
                    and (
                        cover.position is player.position
                        if player.position.value == "GKP"
                        else cover.position.value != "GKP"
                    )
                    for cover in bench
                )
                priority = min(
                    100.0,
                    45
                    + severity * 0.35
                    + (15 if starting else 5)
                    + (8 if starting and not has_cover else 0),
                )
                label = NamedTransferDecisionService._status_label(player.status)
                explanation = (
                    f"{player.web_name} is the leading availability concern: FPL marks the "
                    f"player {label}"
                    + (f" with a {chance}% chance of playing." if chance is not None else ".")
                    + (
                        " There is no available positional bench cover."
                        if starting and not has_cover
                        else ""
                    )
                )
                concern_rows.append(
                    (priority, 0 if starting else 1, player, ConcernKind.AVAILABILITY, explanation)
                )
            elif player.starts >= 3 and player.minutes / max(player.starts * 90, 90) < 0.72:
                reliability = player.minutes / max(player.starts * 90, 90)
                priority = 25 + (1 - reliability) * 35 + (12 if starting else 0)
                concern_rows.append(
                    (
                        priority,
                        0 if starting else 1,
                        player,
                        ConcernKind.MINUTES,
                        f"{player.web_name} has played {reliability:.0%} of a full match per "
                        "recorded start, creating a minutes-reliability concern.",
                    )
                )

            best_for_player: SquadActionCandidate | None = None
            for incoming in catalogue.players.values():
                if (
                    incoming.id in squad_ids
                    or incoming.position is not player.position
                    or incoming.status != "a"
                ):
                    continue
                legality = self._legality.validate(
                    snapshot=snapshot,
                    catalogue=catalogue,
                    state=state,
                    transfers=(
                        ProposedTransfer(
                            outgoing_player_id=player.id,
                            incoming_player_id=incoming.id,
                        ),
                    ),
                )
                if legality.status is not TransferLegalityStatus.LEGAL:
                    continue
                assert legality.remaining_bank is not None
                assert state.free_transfers is not None
                raw_gain = round(scores[incoming.id] - scores[player.id], 1)
                priority_bonus = next(
                    (row[0] * 0.25 for row in concern_rows if row[2].id == player.id), 0
                )
                adjusted = round(
                    raw_gain
                    + priority_bonus
                    + (2 if starting else 0)
                    - legality.points_hit * policy.hit_score_penalty,
                    1,
                )
                action = SquadActionCandidate(
                    action=SquadActionKind.TRANSFER,
                    outgoing=player,
                    incoming=incoming,
                    evidence_gain=raw_gain,
                    policy_adjusted_gain=adjusted,
                    remaining_bank=legality.remaining_bank,
                    free_transfers_used=legality.free_transfers_used,
                    free_transfers_after=max(0, state.free_transfers - 1),
                    points_hit=legality.points_hit,
                    budget_status=budget_status,
                    explanation=(
                        f"Screen {player.web_name} to {incoming.web_name} using "
                        f"{player.web_name}'s current £{player.current_price.tenths / 10:.1f}m "
                        "price as the maximum possible selling value; this route is "
                        "provisional, not yet confirmed affordable or legal."
                        if budget_status == "optimistic"
                        else f"Sell {player.web_name} for {incoming.web_name}; the legal route "
                        f"improves the evidence ranking by {raw_gain:.1f}, leaves "
                        f"£{legality.remaining_bank.tenths / 10:.1f}m and "
                        + (
                            f"costs {legality.points_hit} points."
                            if legality.points_hit
                            else "uses one free transfer."
                        )
                    ),
                )
                if best_for_player is None or self._action_key(action) < self._action_key(
                    best_for_player
                ):
                    best_for_player = action
            if best_for_player is not None:
                actions.append(best_for_player)
                if not any(row[2].id == player.id for row in concern_rows):
                    priority = min(
                        60.0, max(0.0, best_for_player.evidence_gain + (8 if starting else 0))
                    )
                    if priority > 0:
                        concern_rows.append(
                            (
                                priority,
                                0 if starting else 1,
                                player,
                                ConcernKind.UPGRADE,
                                (
                                    f"{player.web_name} has a provisional upgrade opportunity "
                                    f"worth {best_for_player.evidence_gain:.1f} evidence-ranking "
                                    "points before selling-price validation."
                                    if budget_status == "optimistic"
                                    else f"{player.web_name} has a legal upgrade worth "
                                    f"{best_for_player.evidence_gain:.1f} evidence-ranking points."
                                ),
                            )
                        )

        actions.sort(key=self._action_key)
        if not concern_rows:
            weakest = min(snapshot.picks, key=lambda pick: (scores[pick.player.id], pick.player.id))
            concern_rows.append(
                (
                    0.0,
                    0 if weakest.squad_position <= catalogue.rules.starting_size else 1,
                    weakest.player,
                    ConcernKind.UPGRADE,
                    "No availability, minutes or material upgrade concern clears the current "
                    "action threshold.",
                )
            )
        concern_rows.sort(key=lambda row: (-row[0], row[1], row[2].id, row[3].value))
        concerns = tuple(
            RankedSquadConcern(
                rank=index,
                player=row[2],
                kind=row[3],
                priority_score=round(row[0], 1),
                starting_slot=row[1] == 0,
                explanation=row[4],
            )
            for index, row in enumerate(concern_rows[:5], start=1)
        )
        return concerns, actions

    @staticmethod
    def _action_key(action: SquadActionCandidate) -> tuple[float, int, int, int, int]:
        assert action.outgoing is not None and action.incoming is not None
        return (
            -action.policy_adjusted_gain,
            action.points_hit,
            -action.remaining_bank.tenths,
            action.outgoing.id,
            action.incoming.id,
        )

    @staticmethod
    def _same_route(left: SquadActionCandidate, right: SquadActionCandidate) -> bool:
        return (
            left.action is right.action
            and left.outgoing is not None
            and right.outgoing is not None
            and left.incoming is not None
            and right.incoming is not None
            and left.outgoing.id == right.outgoing.id
            and left.incoming.id == right.incoming.id
        )

    @staticmethod
    def _confirm_selected_concern(
        concerns: tuple[RankedSquadConcern, ...], action: SquadActionCandidate
    ) -> tuple[RankedSquadConcern, ...]:
        assert action.outgoing is not None
        return tuple(
            concern.model_copy(
                update={
                    "explanation": (
                        f"{action.outgoing.web_name} has a legal upgrade worth "
                        f"{action.evidence_gain:.1f} evidence-ranking points after exact "
                        "selling-price validation."
                    )
                }
            )
            if concern.player.id == action.outgoing.id and concern.kind is ConcernKind.UPGRADE
            else concern
            for concern in concerns
        )

    @staticmethod
    def _roll_action(
        snapshot: SquadSnapshot, state: TransferPlanningState, catalogue: FplCatalogue
    ) -> SquadActionCandidate:
        assert state.bank is not None and state.free_transfers is not None
        cap = catalogue.rules.maximum_extra_free_transfers + 1
        after = min(cap, state.free_transfers + 1)
        return SquadActionCandidate(
            action=SquadActionKind.ROLL,
            evidence_gain=0,
            policy_adjusted_gain=0,
            remaining_bank=state.bank,
            free_transfers_used=0,
            free_transfers_after=after,
            points_hit=0,
            budget_status="not_applicable",
            explanation=(
                f"Roll the transfer, keep £{state.bank.tenths / 10:.1f}m and carry "
                f"{after} free transfer{'s' if after != 1 else ''} into the next Gameweek."
            ),
        )

    @staticmethod
    def _evidence_ids(
        concerns: tuple[RankedSquadConcern, ...], action: SquadActionCandidate | None
    ) -> tuple[int, ...]:
        ids = [concerns[0].player.id]
        if action is not None:
            assert action.outgoing is not None and action.incoming is not None
            ids.extend((action.outgoing.id, action.incoming.id))
        return tuple(dict.fromkeys(ids))

    @staticmethod
    def _confidence(
        *,
        evidence_ids: tuple[int, ...],
        histories: dict[int, FplElementSummary],
        catalogue: FplCatalogue,
        created_at: datetime,
        separation: float,
    ) -> SquadActionConfidence:
        fresh = timedelta(0) <= created_at - catalogue.retrieved_at <= timedelta(minutes=15)
        complete = all(player_id in histories for player_id in evidence_ids)
        sample = min(catalogue.players[player_id].starts for player_id in evidence_ids)
        reasons = (
            "FPL evidence was retrieved within the 15-minute freshness threshold."
            if fresh
            else "FPL evidence is older than the 15-minute freshness threshold.",
            f"Per-Gameweek history is {'complete' if complete else 'incomplete'} for the "
            "material players.",
            f"The smallest material current-season sample is {sample} starts.",
            f"The leading transfer is {separation:.1f} policy-adjusted points above rolling.",
        )
        if fresh and complete and sample >= 5 and separation >= 12:
            level = ConfidenceLevel.HIGH
        elif fresh and complete and sample >= 3 and separation >= 5:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW
        return SquadActionConfidence(level=level, reasons=reasons)

    @staticmethod
    def _hit_analysis(action: SquadActionCandidate | None, policy: Policy) -> HitAnalysis:
        if action is None or not action.points_hit:
            gain = action.policy_adjusted_gain if action is not None else 0
            return HitAnalysis(
                points_hit=0,
                justified=False,
                transfer_adjusted_gain=gain,
                required_gain=policy.roll_threshold,
                comparison="The leading route uses no hit; rolling remains the zero-cost baseline.",
            )
        justified = action.policy_adjusted_gain >= policy.hit_threshold
        return HitAnalysis(
            points_hit=action.points_hit,
            justified=justified,
            transfer_adjusted_gain=action.policy_adjusted_gain,
            required_gain=policy.hit_threshold,
            comparison=(
                f"The {action.points_hit}-point hit produces {action.policy_adjusted_gain:.1f} "
                f"policy-adjusted gain versus a {policy.hit_threshold:.1f} requirement; it is "
                f"{'justified' if justified else 'not justified'} under this risk policy."
            ),
        )

    @staticmethod
    def _roll_comparison(action: SquadActionCandidate, policy: Policy) -> str:
        if action.action is SquadActionKind.ROLL:
            return (
                "No supported legal route clears the documented "
                f"{policy.roll_threshold:.1f}-point action threshold, so rolling preserves value."
            )
        if action.budget_status == "optimistic":
            return (
                f"The optimistic screen clears the {policy.roll_threshold:.1f}-point threshold "
                f"with {action.policy_adjusted_gain:.1f} adjusted gain; exact selling-price "
                "validation is still required."
            )
        return (
            f"The selected route clears the {policy.roll_threshold:.1f}-point roll threshold "
            f"with {action.policy_adjusted_gain:.1f} policy-adjusted gain."
        )

    @staticmethod
    def _planning_impact(action: SquadActionCandidate, state: TransferPlanningState) -> str:
        assert state.free_transfers is not None
        if action.action is SquadActionKind.ROLL:
            return (
                f"Doing nothing now preserves the squad and increases free transfers from "
                f"{state.free_transfers} to {action.free_transfers_after} for the next decision."
            )
        assert action.outgoing is not None and action.incoming is not None
        return (
            f"The move changes {action.outgoing.web_name} to {action.incoming.web_name}, carries "
            f"£{action.remaining_bank.tenths / 10:.1f}m forward and leaves "
            f"{action.free_transfers_after} free transfers after this Gameweek's action."
        )
