from datetime import datetime, timedelta
from time import perf_counter
from typing import Literal

from gaffertalk_api.domain.models import (
    Fixture,
    FplCatalogue,
    Money,
    Player,
    Position,
    SquadSnapshot,
)
from gaffertalk_api.domain.pro_research import (
    ConfidenceLevel,
    GroundedReason,
    RiskPreference,
    SquadActionConfidence,
)
from gaffertalk_api.domain.route_research import (
    RouteResearchReport,
    RouteSearchConstraints,
    RouteSearchStats,
    RouteSearchStatus,
    RouteTransfer,
    RouteVerdict,
    TransferRouteCandidate,
)
from gaffertalk_api.domain.transfers import (
    ProposedTransfer,
    TransferLegalityStatus,
    TransferPlanningState,
)
from gaffertalk_api.integrations.fpl.schemas import FplElementSummary
from gaffertalk_api.services.named_transfer_decisions import NamedTransferDecisionService
from gaffertalk_api.services.squad_action_decisions import POLICIES
from gaffertalk_api.services.transfer_legality import TransferLegalityService

MAX_SECONDARY_CANDIDATES_PER_POSITION = 40


class RouteResearchService:
    """Find bounded target routes; language models never generate or rank candidates."""

    def __init__(self, legality: TransferLegalityService | None = None) -> None:
        self._legality = legality or TransferLegalityService()
        self._evidence = NamedTransferDecisionService(self._legality)

    def preview_evidence_ids(
        self,
        *,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        fixtures: tuple[Fixture, ...],
        state: TransferPlanningState,
        target_player_id: int,
        preserved_player_ids: tuple[int, ...],
        excluded_player_ids: tuple[int, ...],
        minimum_remaining_bank: Money,
        maximum_transfers: Literal[1, 2],
        risk_preference: RiskPreference,
        purchase_prices: dict[int, Money],
    ) -> tuple[int, ...]:
        target, preserved, excluded = self._validate_inputs(
            snapshot,
            catalogue,
            state,
            target_player_id,
            preserved_player_ids,
            excluded_player_ids,
            purchase_prices,
        )
        fixture_runs = self._evidence._fixture_runs(fixtures)
        scores = {
            player.id: self._evidence._score(player, fixture_runs.get(player.club.id))
            for player in catalogue.players.values()
        }
        routes, _ = self._enumerate(
            snapshot=snapshot,
            catalogue=catalogue,
            state=self._optimistic_state(snapshot, catalogue, state),
            target=target,
            preserved=preserved,
            excluded=excluded,
            minimum_remaining_bank=minimum_remaining_bank,
            maximum_transfers=maximum_transfers,
            risk_preference=risk_preference,
            scores=scores,
            budget_status="optimistic",
        )
        ids = [target.id]
        if routes:
            for transfer in routes[0].transfers:
                ids.extend((transfer.outgoing.id, transfer.incoming.id))
        return tuple(dict.fromkeys(ids))

    def research(
        self,
        *,
        squad_name: str,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        fixtures: tuple[Fixture, ...],
        state: TransferPlanningState,
        target_player_id: int,
        preserved_player_ids: tuple[int, ...],
        excluded_player_ids: tuple[int, ...],
        minimum_remaining_bank: Money,
        maximum_transfers: Literal[1, 2],
        risk_preference: RiskPreference,
        proceed_if_discouraged: bool,
        purchase_prices: dict[int, Money],
        histories: dict[int, FplElementSummary],
        created_at: datetime,
    ) -> RouteResearchReport:
        started = perf_counter()
        target, preserved, excluded = self._validate_inputs(
            snapshot,
            catalogue,
            state,
            target_player_id,
            preserved_player_ids,
            excluded_player_ids,
            purchase_prices,
        )
        fixture_runs = self._evidence._fixture_runs(fixtures)
        scores = {
            player.id: self._evidence._score(player, fixture_runs.get(player.club.id))
            for player in catalogue.players.values()
        }
        optimistic_routes, examined = self._enumerate(
            snapshot=snapshot,
            catalogue=catalogue,
            state=self._optimistic_state(snapshot, catalogue, state),
            target=target,
            preserved=preserved,
            excluded=excluded,
            minimum_remaining_bank=minimum_remaining_bank,
            maximum_transfers=maximum_transfers,
            risk_preference=risk_preference,
            scores=scores,
            budget_status="optimistic",
        )
        status = RouteSearchStatus.NO_LEGAL_ROUTE
        recommended: TransferRouteCandidate | None = None
        provisional: TransferRouteCandidate | None = None
        requested: tuple[Player, ...] = ()
        material = optimistic_routes[0] if optimistic_routes else None
        for optimistic in optimistic_routes:
            missing = tuple(
                transfer.outgoing
                for transfer in optimistic.transfers
                if transfer.outgoing.id not in state.selling_prices
            )
            if missing:
                status = RouteSearchStatus.NEEDS_SELLING_PRICES
                provisional = optimistic
                requested = missing
                material = optimistic
                break
            exact = self._build_candidate(
                snapshot=snapshot,
                catalogue=catalogue,
                state=state,
                transfers=tuple(
                    ProposedTransfer(
                        outgoing_player_id=transfer.outgoing.id,
                        incoming_player_id=transfer.incoming.id,
                    )
                    for transfer in optimistic.transfers
                ),
                minimum_remaining_bank=minimum_remaining_bank,
                risk_preference=risk_preference,
                scores=scores,
                budget_status="exact",
            )
            examined += 1
            if exact is not None:
                status = RouteSearchStatus.ROUTE
                recommended = exact
                material = exact
                break

        policy = POLICIES[risk_preference]
        lead = recommended or provisional
        if lead is None:
            verdict = RouteVerdict.NO_ROUTE
            strategic = (
                f"No supported one- or {maximum_transfers}-transfer route can add "
                f"{target.web_name} while satisfying the confirmed constraints."
            )
            opportunity = (
                "No financial action is proposed; the current squad and bank remain unchanged."
            )
        else:
            threshold = policy.hit_threshold if lead.points_hit else policy.roll_threshold
            verdict = (
                RouteVerdict.RECOMMENDED
                if lead.policy_adjusted_gain >= threshold
                else RouteVerdict.DISCOURAGED
            )
            strategic = (
                f"The route clears the {threshold:.1f}-point {risk_preference.value} threshold."
                if verdict is RouteVerdict.RECOMMENDED
                else f"A route exists, but its {lead.policy_adjusted_gain:.1f} adjusted gain does "
                f"not clear the {threshold:.1f}-point {risk_preference.value} threshold."
            )
            if verdict is RouteVerdict.DISCOURAGED and proceed_if_discouraged:
                strategic += (
                    " The manager override exposes the strongest route without changing "
                    "that verdict."
                )
            opportunity = (
                (
                    "If the optimistic selling values are confirmed, the route would use "
                    if status is RouteSearchStatus.NEEDS_SELLING_PRICES
                    else "The route uses "
                )
                + f"{lead.free_transfers_used} free transfer"
                f"{'s' if lead.free_transfers_used != 1 else ''}, costs {lead.points_hit} points "
                f"and leaves £{lead.remaining_bank.tenths / 10:.1f}m."
            )
        evidence_ids = [target.id]
        if material is not None:
            for transfer in material.transfers:
                evidence_ids.extend((transfer.outgoing.id, transfer.incoming.id))
        evidence_ids = list(dict.fromkeys(evidence_ids))
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
            evidence_ids=tuple(evidence_ids),
            histories=histories,
            catalogue=catalogue,
            created_at=created_at,
            separation=abs(lead.policy_adjusted_gain) if lead else 0,
        )
        if status is RouteSearchStatus.NEEDS_SELLING_PRICES:
            action_reason = (
                "This route is an optimistic screen, not a legal recommendation. Confirm "
                + " and ".join(player.web_name for player in requested)
                + " selling price"
                + ("s" if len(requested) > 1 else "")
                + " to validate it."
            )
        elif status is RouteSearchStatus.ROUTE:
            action_reason = recommended.explanation if recommended else strategic
        else:
            action_reason = strategic
        constraints = RouteSearchConstraints(
            preserved_players=tuple(catalogue.players[player_id] for player_id in preserved),
            excluded_players=tuple(catalogue.players[player_id] for player_id in excluded),
            minimum_remaining_bank=minimum_remaining_bank,
            maximum_transfers=maximum_transfers,
        )
        alternatives: tuple[TransferRouteCandidate, ...] = ()
        if status is RouteSearchStatus.ROUTE and recommended is not None:
            exact_alternatives: list[TransferRouteCandidate] = []
            for optimistic in optimistic_routes:
                if self._route_key(optimistic) == self._route_key(recommended):
                    continue
                if any(
                    transfer.outgoing.id not in state.selling_prices
                    for transfer in optimistic.transfers
                ):
                    continue
                exact_alternative = self._build_candidate(
                    snapshot=snapshot,
                    catalogue=catalogue,
                    state=state,
                    transfers=tuple(
                        ProposedTransfer(
                            outgoing_player_id=transfer.outgoing.id,
                            incoming_player_id=transfer.incoming.id,
                        )
                        for transfer in optimistic.transfers
                    ),
                    minimum_remaining_bank=minimum_remaining_bank,
                    risk_preference=risk_preference,
                    scores=scores,
                    budget_status="exact",
                )
                examined += 1
                if exact_alternative is not None:
                    exact_alternatives.append(exact_alternative)
                if len(exact_alternatives) == 3:
                    break
            alternatives = tuple(exact_alternatives)
        grounded = (
            GroundedReason(id="route", text=action_reason),
            GroundedReason(id="strategy", text=strategic),
            GroundedReason(id="opportunity_cost", text=opportunity),
        )
        return RouteResearchReport(
            squad_name=squad_name,
            created_at=created_at,
            data_retrieved_at=catalogue.retrieved_at,
            risk_preference=risk_preference,
            target=target,
            constraints=constraints,
            status=status,
            verdict=verdict,
            manager_override=proceed_if_discouraged,
            recommended_route=recommended,
            provisional_route=provisional,
            requested_selling_prices_for=requested,
            alternatives=alternatives,
            strategic_explanation=strategic,
            opportunity_cost=opportunity,
            confidence=confidence,
            evidence=evidence,
            assumptions=(
                "Current FPL prices are optimistic upper bounds until each proposed outgoing "
                "player's selling price is confirmed.",
                "Confirmed selling prices already incorporate purchase-price effects; optional "
                "purchase prices are used only to cross-check that calculation.",
                f"The search is capped at {maximum_transfers} current-Gameweek transfers and "
                f"{MAX_SECONDARY_CANDIDATES_PER_POSITION} secondary candidates per position.",
                "Chips and routes longer than two transfers are unsupported.",
            ),
            grounded_reasons=grounded,
            search_stats=RouteSearchStats(
                routes_examined=examined,
                optimistic_routes=len(optimistic_routes),
                candidate_limit_per_position=MAX_SECONDARY_CANDIDATES_PER_POSITION,
                elapsed_milliseconds=round((perf_counter() - started) * 1000, 2),
            ),
        )

    def _enumerate(
        self,
        *,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        state: TransferPlanningState,
        target: Player,
        preserved: tuple[int, ...],
        excluded: tuple[int, ...],
        minimum_remaining_bank: Money,
        maximum_transfers: Literal[1, 2],
        risk_preference: RiskPreference,
        scores: dict[int, float],
        budget_status: Literal["optimistic", "exact"],
    ) -> tuple[list[TransferRouteCandidate], int]:
        if target.status != "a" or target.id in excluded:
            return [], 0
        squad_ids = {pick.player.id for pick in snapshot.picks}
        if target.id in squad_ids:
            return [], 0
        required_out = set(excluded) & squad_ids
        available_out = [pick.player for pick in snapshot.picks if pick.player.id not in preserved]
        routes: list[TransferRouteCandidate] = []
        examined = 0
        for primary in available_out:
            if primary.position is not target.position:
                continue
            one = (
                ProposedTransfer(
                    outgoing_player_id=primary.id,
                    incoming_player_id=target.id,
                ),
            )
            if required_out.issubset({primary.id}):
                examined += 1
                candidate = self._build_candidate(
                    snapshot=snapshot,
                    catalogue=catalogue,
                    state=state,
                    transfers=one,
                    minimum_remaining_bank=minimum_remaining_bank,
                    risk_preference=risk_preference,
                    scores=scores,
                    budget_status=budget_status,
                )
                if candidate is not None:
                    routes.append(candidate)
            if maximum_transfers < 2:
                continue
            for secondary_out in available_out:
                if secondary_out.id == primary.id:
                    continue
                if not required_out.issubset({primary.id, secondary_out.id}):
                    continue
                for secondary_in in self._candidate_pool(
                    catalogue, scores, secondary_out.position, squad_ids, excluded, target.id
                ):
                    examined += 1
                    candidate = self._build_candidate(
                        snapshot=snapshot,
                        catalogue=catalogue,
                        state=state,
                        transfers=(
                            ProposedTransfer(
                                outgoing_player_id=primary.id,
                                incoming_player_id=target.id,
                            ),
                            ProposedTransfer(
                                outgoing_player_id=secondary_out.id,
                                incoming_player_id=secondary_in.id,
                            ),
                        ),
                        minimum_remaining_bank=minimum_remaining_bank,
                        risk_preference=risk_preference,
                        scores=scores,
                        budget_status=budget_status,
                    )
                    if candidate is not None:
                        routes.append(candidate)
        routes.sort(key=self._candidate_sort_key)
        unique: dict[tuple[tuple[int, int], ...], TransferRouteCandidate] = {}
        for route in routes:
            unique.setdefault(self._route_key(route), route)
        return list(unique.values()), examined

    def _build_candidate(
        self,
        *,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        state: TransferPlanningState,
        transfers: tuple[ProposedTransfer, ...],
        minimum_remaining_bank: Money,
        risk_preference: RiskPreference,
        scores: dict[int, float],
        budget_status: Literal["optimistic", "exact"],
    ) -> TransferRouteCandidate | None:
        legality = self._legality.validate(
            snapshot=snapshot,
            catalogue=catalogue,
            state=state,
            transfers=transfers,
        )
        if (
            legality.status is not TransferLegalityStatus.LEGAL
            or legality.remaining_bank is None
            or legality.remaining_bank.tenths < minimum_remaining_bank.tenths
        ):
            return None
        assert state.free_transfers is not None
        raw_gain = round(
            sum(scores[transfer.incoming_player_id] for transfer in transfers)
            - sum(scores[transfer.outgoing_player_id] for transfer in transfers),
            1,
        )
        policy = POLICIES[risk_preference]
        adjusted = round(raw_gain - legality.points_hit * policy.hit_score_penalty, 1)
        route_transfers = tuple(
            RouteTransfer(
                outgoing=catalogue.players[transfer.outgoing_player_id],
                incoming=catalogue.players[transfer.incoming_player_id],
                confirmed_selling_price=(
                    state.selling_prices[transfer.outgoing_player_id]
                    if budget_status == "exact"
                    else None
                ),
            )
            for transfer in transfers
        )
        source = {pick.player.id for pick in snapshot.picks}
        resulting = tuple(
            sorted(
                (source - {transfer.outgoing_player_id for transfer in transfers})
                | {transfer.incoming_player_id for transfer in transfers}
            )
        )
        pairs = ", ".join(
            f"{transfer.outgoing.web_name} → {transfer.incoming.web_name}"
            for transfer in route_transfers
        )
        explanation = (
            f"Screen {pairs} using current prices only as maximum selling values; this route "
            "is not yet confirmed affordable or legal."
            if budget_status == "optimistic"
            else f"The exact legal route {pairs} leaves "
            f"£{legality.remaining_bank.tenths / 10:.1f}m, "
            f"uses {legality.free_transfers_used} free transfer"
            f"{'s' if legality.free_transfers_used != 1 else ''} and costs "
            f"{legality.points_hit} points."
        )
        return TransferRouteCandidate(
            transfers=route_transfers,
            budget_status=budget_status,
            evidence_gain=raw_gain,
            policy_adjusted_gain=adjusted,
            remaining_bank=legality.remaining_bank,
            free_transfers_used=legality.free_transfers_used,
            free_transfers_after=max(0, state.free_transfers - len(transfers)),
            points_hit=legality.points_hit,
            resulting_player_ids=resulting,
            explanation=explanation,
        )

    @staticmethod
    def _candidate_pool(
        catalogue: FplCatalogue,
        scores: dict[int, float],
        position: Position,
        squad_ids: set[int],
        excluded: tuple[int, ...],
        target_id: int,
    ) -> tuple[Player, ...]:
        eligible = [
            player
            for player in catalogue.players.values()
            if player.position is position
            and player.id not in squad_ids
            and player.id not in excluded
            and player.id != target_id
            and player.status == "a"
        ]
        by_quality = sorted(eligible, key=lambda player: (-scores[player.id], player.id))[:30]
        by_price = sorted(
            eligible,
            key=lambda player: (player.current_price.tenths, -scores[player.id], player.id),
        )[:10]
        return tuple(dict.fromkeys([*by_quality, *by_price]))[
            :MAX_SECONDARY_CANDIDATES_PER_POSITION
        ]

    @staticmethod
    def _candidate_sort_key(
        route: TransferRouteCandidate,
    ) -> tuple[float, int, int, tuple[int, ...]]:
        return (
            -route.policy_adjusted_gain,
            route.points_hit,
            -route.remaining_bank.tenths,
            tuple(value for pair in RouteResearchService._route_key(route) for value in pair),
        )

    @staticmethod
    def _route_key(route: TransferRouteCandidate) -> tuple[tuple[int, int], ...]:
        return tuple(
            sorted((transfer.outgoing.id, transfer.incoming.id) for transfer in route.transfers)
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
    def _validate_inputs(
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        state: TransferPlanningState,
        target_player_id: int,
        preserved_player_ids: tuple[int, ...],
        excluded_player_ids: tuple[int, ...],
        purchase_prices: dict[int, Money],
    ) -> tuple[Player, tuple[int, ...], tuple[int, ...]]:
        if state.bank is None or state.free_transfers is None:
            raise ValueError("confirm bank and free transfers before route research")
        if target_player_id not in catalogue.players:
            raise ValueError("the target player is not in the current FPL catalogue")
        if not set(excluded_player_ids).issubset(catalogue.players):
            raise ValueError("excluded players must exist in the current FPL catalogue")
        squad_ids = {pick.player.id for pick in snapshot.picks}
        if not set(preserved_player_ids).issubset(squad_ids):
            raise ValueError("preserved players must belong to the confirmed squad")
        if set(preserved_player_ids) & set(excluded_player_ids):
            raise ValueError("a player cannot be both preserved and excluded")
        if len(set(excluded_player_ids) & squad_ids) > 2:
            raise ValueError("at most two owned players can be excluded from a two-transfer route")
        if not set(state.selling_prices).issubset(squad_ids):
            raise ValueError("selling prices may only reference players in the squad")
        for player_id, price in state.selling_prices.items():
            current = catalogue.players[player_id].current_price.tenths
            if price.tenths > current:
                raise ValueError("a confirmed selling price cannot exceed current FPL price")
            purchase = purchase_prices.get(player_id)
            if purchase is not None:
                expected = (
                    current
                    if current <= purchase.tenths
                    else purchase.tenths + (current - purchase.tenths) // 2
                )
                if price.tenths != expected:
                    raise ValueError(
                        f"selling price for {catalogue.players[player_id].web_name} does not "
                        "match its supplied purchase price and current FPL price"
                    )
        return (
            catalogue.players[target_player_id],
            tuple(dict.fromkeys(preserved_player_ids)),
            tuple(dict.fromkeys(excluded_player_ids)),
        )

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
            "FPL evidence is within the 15-minute freshness threshold."
            if fresh
            else "FPL evidence is older than the 15-minute freshness threshold.",
            f"Per-Gameweek history is {'complete' if complete else 'incomplete'} for "
            "route players.",
            f"The smallest current-season sample is {sample} starts.",
            f"The route's absolute policy-adjusted separation is {separation:.1f} points.",
        )
        if fresh and complete and sample >= 5 and separation >= 12:
            level = ConfidenceLevel.HIGH
        elif fresh and complete and sample >= 3 and separation >= 5:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW
        return SquadActionConfidence(level=level, reasons=reasons)
