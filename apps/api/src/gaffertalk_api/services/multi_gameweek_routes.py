from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

from gaffertalk_api.domain.models import DataProvenance, FplCatalogue, Player
from gaffertalk_api.domain.multi_gameweek_planning import (
    GameweekPlanStep,
    MultiGameweekRoute,
    MultiGameweekRouteReport,
    MultiGameweekRouteRequest,
    MultiGameweekSearchBounds,
    MultiGameweekSearchStats,
    MultiGameweekSearchStatus,
    PlannedTransfer,
    RollAction,
    SellingPriceBasis,
    TransferBatchAction,
)
from gaffertalk_api.domain.transfers import (
    ProposedTransfer,
    TransferLegalityStatus,
    TransferPlanningState,
    TransferRejection,
)
from gaffertalk_api.services.transfer_legality import TransferLegalityService

MAX_TOTAL_TRANSFERS = 3
REPLACEMENTS_PER_OUTGOING = 4
MAX_ROUTE_SIMULATIONS = 25_000

SELECTION_BASIS = (
    "Routes use fewest hit points first, then earliest target arrival, fewest transfers, "
    "highest remaining bank, and stable player IDs. This is a feasibility ordering, not a "
    "football-performance recommendation."
)


@dataclass(frozen=True, slots=True)
class _RouteCandidate:
    route: MultiGameweekRoute
    missing_selling_prices: tuple[int, ...]


class MultiGameweekRouteService:
    """Find bounded, legal target-player routes without forecasting performance."""

    def __init__(self, legality: TransferLegalityService | None = None) -> None:
        self._legality = legality or TransferLegalityService()

    def search(
        self,
        *,
        request: MultiGameweekRouteRequest,
        catalogue: FplCatalogue,
    ) -> MultiGameweekRouteReport:
        gameweeks = {gameweek.id: gameweek for gameweek in catalogue.gameweeks}
        self._validate_request(request, catalogue, set(gameweeks))
        target = catalogue.players[request.target_player_id]
        initial_ids = {pick.player.id for pick in request.state.snapshot.picks}
        bounds = self._bounds()

        if target.id in initial_ids:
            return self._empty_report(
                request=request,
                target=target,
                status=MultiGameweekSearchStatus.TARGET_ALREADY_OWNED,
                bounds=bounds,
            )

        eligible_target_outgoing = tuple(
            player_id
            for player_id in sorted(initial_ids)
            if catalogue.players[player_id].position is target.position
            and player_id not in request.protected_player_ids
        )
        if not eligible_target_outgoing:
            return self._empty_report(
                request=request,
                target=target,
                status=MultiGameweekSearchStatus.NO_LEGAL_ROUTE,
                bounds=bounds,
            )

        blueprints = self._transfer_blueprints(
            request=request,
            catalogue=catalogue,
            target_outgoing_ids=eligible_target_outgoing,
        )
        candidates: list[_RouteCandidate] = []
        simulations = 0
        truncated = False
        last_rejections: tuple[TransferRejection, ...] = ()
        for blueprint in blueprints:
            for schedule in self._schedules(blueprint, request.horizon_gameweek_ids):
                if simulations == MAX_ROUTE_SIMULATIONS:
                    truncated = True
                    break
                simulations += 1
                route, rejections = self._simulate(
                    request=request,
                    catalogue=catalogue,
                    schedule=schedule,
                )
                if route is None:
                    last_rejections = rejections
                    continue
                missing = self._missing_selling_prices(request, route)
                candidates.append(_RouteCandidate(route=route, missing_selling_prices=missing))
            if truncated:
                break

        candidates.sort(key=lambda candidate: self._route_sort_key(candidate.route))
        candidates = self._unique_candidates(candidates)
        stats = MultiGameweekSearchStats(
            transfer_blueprints_generated=len(blueprints),
            route_simulations=simulations,
            valid_routes=len(candidates),
            search_truncated=truncated,
        )
        if not candidates:
            return self._empty_report(
                request=request,
                target=target,
                status=MultiGameweekSearchStatus.NO_ROUTE_FOUND_WITHIN_BOUNDS,
                bounds=bounds,
                stats=stats,
                rejections=last_rejections,
            )

        lead = candidates[0]
        alternatives = self._select_alternatives(candidates[1:], lead.route)
        if lead.missing_selling_prices:
            return self._report(
                request=request,
                target=target,
                status=MultiGameweekSearchStatus.NEEDS_SELLING_PRICES,
                bounds=bounds,
                stats=stats,
                primary=lead.route,
                alternatives=alternatives,
                requested_prices=lead.missing_selling_prices,
            )

        exact_candidates = [
            candidate for candidate in candidates if not candidate.missing_selling_prices
        ]
        alternatives = self._select_alternatives(exact_candidates[1:], lead.route)
        return self._report(
            request=request,
            target=target,
            status=MultiGameweekSearchStatus.ROUTES,
            bounds=bounds,
            stats=stats,
            primary=lead.route,
            alternatives=alternatives,
        )

    @staticmethod
    def _validate_request(
        request: MultiGameweekRouteRequest,
        catalogue: FplCatalogue,
        gameweek_ids: set[int],
    ) -> None:
        if request.target_player_id not in catalogue.players:
            raise ValueError("the target player is not in the current FPL catalogue")
        squad_ids = {pick.player.id for pick in request.state.snapshot.picks}
        missing_squad_players = squad_ids - set(catalogue.players)
        if missing_squad_players:
            raise ValueError("every squad player must exist in the current FPL catalogue")
        missing_gameweeks = set(request.horizon_gameweek_ids) - gameweek_ids
        if missing_gameweeks:
            raise ValueError("every planning Gameweek must exist in the current catalogue")
        if len(request.horizon_gameweek_ids) == 2:
            first, second = request.horizon_gameweek_ids
            if second != first + 1:
                raise ValueError("the two planning Gameweeks must be consecutive")
        if request.horizon_gameweek_ids[0] != request.state.snapshot.gameweek.id + 1:
            raise ValueError("planning must begin with the Gameweek after the confirmed snapshot")
        maximum_free_transfers = catalogue.rules.maximum_extra_free_transfers + 1
        if request.state.free_transfers > maximum_free_transfers:
            raise ValueError("confirmed free transfers exceed the current FPL rules")

    def _transfer_blueprints(
        self,
        *,
        request: MultiGameweekRouteRequest,
        catalogue: FplCatalogue,
        target_outgoing_ids: tuple[int, ...],
    ) -> tuple[tuple[ProposedTransfer, ...], ...]:
        initial_ids = {pick.player.id for pick in request.state.snapshot.picks}
        protected = set(request.protected_player_ids)
        target_id = request.target_player_id
        funding_options: list[tuple[int, ProposedTransfer]] = []
        for outgoing_id in sorted(initial_ids - protected):
            outgoing = catalogue.players[outgoing_id]
            eligible = [
                player
                for player in catalogue.players.values()
                if player.position is outgoing.position
                and player.id not in initial_ids
                and player.id != target_id
                and player.current_price.tenths < outgoing.current_price.tenths
            ]
            eligible.sort(key=lambda player: (player.current_price.tenths, player.id))
            for incoming in eligible[:REPLACEMENTS_PER_OUTGOING]:
                released = outgoing.current_price.tenths - incoming.current_price.tenths
                funding_options.append(
                    (
                        released,
                        ProposedTransfer(
                            outgoing_player_id=outgoing_id,
                            incoming_player_id=incoming.id,
                        ),
                    )
                )
        funding_options.sort(
            key=lambda item: (
                -item[0],
                item[1].outgoing_player_id,
                item[1].incoming_player_id,
            )
        )

        blueprints: dict[tuple[tuple[int, int], ...], tuple[ProposedTransfer, ...]] = {}
        for target_outgoing_id in target_outgoing_ids:
            target_transfer = ProposedTransfer(
                outgoing_player_id=target_outgoing_id,
                incoming_player_id=target_id,
            )
            self._add_blueprint(blueprints, (target_transfer,))
            compatible = [
                option
                for _, option in funding_options
                if option.outgoing_player_id != target_outgoing_id
            ]
            for funding in compatible:
                self._add_blueprint(blueprints, (funding, target_transfer))
            for first, second in combinations(compatible, 2):
                if first.outgoing_player_id == second.outgoing_player_id:
                    continue
                if first.incoming_player_id == second.incoming_player_id:
                    continue
                self._add_blueprint(blueprints, (first, second, target_transfer))
        return tuple(blueprints.values())

    @staticmethod
    def _add_blueprint(
        blueprints: dict[tuple[tuple[int, int], ...], tuple[ProposedTransfer, ...]],
        transfers: tuple[ProposedTransfer, ...],
    ) -> None:
        if len(transfers) > MAX_TOTAL_TRANSFERS:
            return
        key = tuple(
            (transfer.outgoing_player_id, transfer.incoming_player_id) for transfer in transfers
        )
        blueprints.setdefault(key, transfers)

    @staticmethod
    def _schedules(
        blueprint: tuple[ProposedTransfer, ...],
        gameweek_ids: tuple[int, ...],
    ) -> tuple[tuple[tuple[int, tuple[ProposedTransfer, ...]], ...], ...]:
        first = gameweek_ids[0]
        schedules: list[tuple[tuple[int, tuple[ProposedTransfer, ...]], ...]] = [
            ((first, blueprint),)
        ]
        if len(gameweek_ids) == 1:
            return tuple(schedules)
        second = gameweek_ids[1]
        schedules.append(((first, ()), (second, blueprint)))
        for split_at in range(1, len(blueprint)):
            schedules.append(
                (
                    (first, blueprint[:split_at]),
                    (second, blueprint[split_at:]),
                )
            )
        return tuple(schedules)

    def _simulate(
        self,
        *,
        request: MultiGameweekRouteRequest,
        catalogue: FplCatalogue,
        schedule: tuple[tuple[int, tuple[ProposedTransfer, ...]], ...],
    ) -> tuple[MultiGameweekRoute | None, tuple[TransferRejection, ...]]:
        snapshot = request.state.snapshot
        bank = request.state.bank
        free_transfers = request.state.free_transfers
        total_hit = 0
        total_transfers = 0
        target_arrival: int | None = None
        steps: list[GameweekPlanStep] = []
        maximum_free_transfers = catalogue.rules.maximum_extra_free_transfers + 1

        for gameweek_id, transfers in schedule:
            if not transfers:
                next_free_transfers = min(maximum_free_transfers, free_transfers + 1)
                steps.append(
                    GameweekPlanStep(
                        gameweek_id=gameweek_id,
                        action=RollAction(),
                        bank_before=bank,
                        bank_after=bank,
                        free_transfers_before=free_transfers,
                        free_transfers_used=0,
                        free_transfers_next_gameweek=next_free_transfers,
                        points_hit=0,
                        resulting_player_ids=tuple(
                            sorted(pick.player.id for pick in snapshot.picks)
                        ),
                    )
                )
                free_transfers = next_free_transfers
                continue

            current_ids = {pick.player.id for pick in snapshot.picks}
            selling_prices = {
                player_id: request.state.selling_prices.get(
                    player_id,
                    catalogue.players[player_id].current_price,
                )
                for player_id in current_ids
            }
            legality = self._legality.validate(
                snapshot=snapshot,
                catalogue=catalogue,
                state=TransferPlanningState(
                    bank=bank,
                    free_transfers=free_transfers,
                    selling_prices=selling_prices,
                ),
                transfers=transfers,
            )
            if legality.status is not TransferLegalityStatus.LEGAL:
                return None, legality.rejections
            assert legality.remaining_bank is not None

            planned_transfers = tuple(
                PlannedTransfer(
                    outgoing=catalogue.players[transfer.outgoing_player_id],
                    incoming=catalogue.players[transfer.incoming_player_id],
                    selling_price_used=selling_prices[transfer.outgoing_player_id],
                    selling_price_basis=(
                        SellingPriceBasis.MANAGER_CONFIRMED
                        if transfer.outgoing_player_id in request.state.selling_prices
                        else SellingPriceBasis.CURRENT_PRICE_UPPER_BOUND
                    ),
                    purchase_price_used=catalogue.players[
                        transfer.incoming_player_id
                    ].current_price,
                )
                for transfer in transfers
            )
            replacement_by_outgoing = {
                transfer.outgoing_player_id: catalogue.players[transfer.incoming_player_id]
                for transfer in transfers
            }
            new_picks = tuple(
                pick.model_copy(
                    update={"player": replacement_by_outgoing.get(pick.player.id, pick.player)}
                )
                for pick in snapshot.picks
            )
            snapshot = snapshot.model_copy(
                update={
                    "gameweek": next(
                        gameweek for gameweek in catalogue.gameweeks if gameweek.id == gameweek_id
                    ),
                    "picks": new_picks,
                    "bank": legality.remaining_bank,
                    "event_transfers": len(transfers),
                    "event_transfer_cost": legality.points_hit,
                    "active_chip": None,
                    "provenance": DataProvenance.DERIVED,
                }
            )
            next_free_transfers = min(
                maximum_free_transfers,
                max(0, free_transfers - legality.free_transfers_used) + 1,
            )
            total_hit += legality.points_hit
            total_transfers += len(transfers)
            bank_before = bank
            bank = legality.remaining_bank
            free_transfers_before = free_transfers
            free_transfers = next_free_transfers
            resulting_ids = tuple(sorted(pick.player.id for pick in snapshot.picks))
            if request.target_player_id in resulting_ids and target_arrival is None:
                target_arrival = gameweek_id
            steps.append(
                GameweekPlanStep(
                    gameweek_id=gameweek_id,
                    action=TransferBatchAction(transfers=transfers),
                    transfers=planned_transfers,
                    bank_before=bank_before,
                    bank_after=bank,
                    free_transfers_before=free_transfers_before,
                    free_transfers_used=legality.free_transfers_used,
                    free_transfers_next_gameweek=next_free_transfers,
                    points_hit=legality.points_hit,
                    resulting_player_ids=resulting_ids,
                )
            )
            if total_hit > request.maximum_points_hit:
                return None, ()

        resulting_ids = tuple(sorted(pick.player.id for pick in snapshot.picks))
        if target_arrival is None:
            return None, ()
        if bank.tenths < request.minimum_remaining_bank.tenths:
            return None, ()
        return (
            MultiGameweekRoute(
                steps=tuple(steps),
                target=catalogue.players[request.target_player_id],
                target_arrival_gameweek_id=target_arrival,
                total_transfers=total_transfers,
                total_points_hit=total_hit,
                remaining_bank=bank,
                resulting_player_ids=resulting_ids,
            ),
            (),
        )

    @staticmethod
    def _missing_selling_prices(
        request: MultiGameweekRouteRequest,
        route: MultiGameweekRoute,
    ) -> tuple[int, ...]:
        initial_ids = {pick.player.id for pick in request.state.snapshot.picks}
        missing = {
            transfer.outgoing.id
            for step in route.steps
            for transfer in step.transfers
            if transfer.outgoing.id in initial_ids
            and transfer.outgoing.id not in request.state.selling_prices
        }
        return tuple(sorted(missing))

    @staticmethod
    def _route_sort_key(route: MultiGameweekRoute) -> tuple[object, ...]:
        return (
            route.total_points_hit,
            route.target_arrival_gameweek_id,
            route.total_transfers,
            -route.remaining_bank.tenths,
            tuple(
                (
                    step.gameweek_id,
                    tuple(
                        (transfer.outgoing.id, transfer.incoming.id) for transfer in step.transfers
                    ),
                )
                for step in route.steps
            ),
        )

    @classmethod
    def _unique_candidates(cls, candidates: Iterable[_RouteCandidate]) -> list[_RouteCandidate]:
        unique: dict[tuple[object, ...], _RouteCandidate] = {}
        for candidate in candidates:
            unique.setdefault(cls._route_signature(candidate.route), candidate)
        return list(unique.values())

    @classmethod
    def _select_alternatives(
        cls,
        candidates: Iterable[_RouteCandidate],
        primary: MultiGameweekRoute,
    ) -> tuple[MultiGameweekRoute, ...]:
        alternatives: list[MultiGameweekRoute] = []
        primary_signature = cls._route_signature(primary)
        for candidate in candidates:
            if cls._route_signature(candidate.route) == primary_signature:
                continue
            alternatives.append(candidate.route)
            if len(alternatives) == 2:
                break
        return tuple(alternatives)

    @staticmethod
    def _route_signature(route: MultiGameweekRoute) -> tuple[object, ...]:
        return tuple(
            (
                step.gameweek_id,
                tuple((transfer.outgoing.id, transfer.incoming.id) for transfer in step.transfers),
            )
            for step in route.steps
        )

    @staticmethod
    def _bounds() -> MultiGameweekSearchBounds:
        return MultiGameweekSearchBounds(
            replacements_per_outgoing_player=REPLACEMENTS_PER_OUTGOING,
            maximum_route_simulations=MAX_ROUTE_SIMULATIONS,
        )

    def _empty_report(
        self,
        *,
        request: MultiGameweekRouteRequest,
        target: Player,
        status: MultiGameweekSearchStatus,
        bounds: MultiGameweekSearchBounds,
        stats: MultiGameweekSearchStats | None = None,
        rejections: tuple[TransferRejection, ...] = (),
    ) -> MultiGameweekRouteReport:
        return MultiGameweekRouteReport(
            status=status,
            target=target,
            horizon_gameweek_ids=request.horizon_gameweek_ids,
            selection_basis=SELECTION_BASIS,
            assumptions=self._assumptions(),
            bounds=bounds,
            stats=stats
            or MultiGameweekSearchStats(
                transfer_blueprints_generated=0,
                route_simulations=0,
                valid_routes=0,
                search_truncated=False,
            ),
            rejections=rejections,
        )

    def _report(
        self,
        *,
        request: MultiGameweekRouteRequest,
        target: Player,
        status: MultiGameweekSearchStatus,
        bounds: MultiGameweekSearchBounds,
        stats: MultiGameweekSearchStats,
        primary: MultiGameweekRoute,
        alternatives: tuple[MultiGameweekRoute, ...],
        requested_prices: tuple[int, ...] = (),
    ) -> MultiGameweekRouteReport:
        return MultiGameweekRouteReport(
            status=status,
            target=target,
            horizon_gameweek_ids=request.horizon_gameweek_ids,
            primary_route=primary,
            alternatives=alternatives,
            requested_selling_price_player_ids=requested_prices,
            selection_basis=SELECTION_BASIS,
            assumptions=self._assumptions(),
            bounds=bounds,
            stats=stats,
        )

    @staticmethod
    def _assumptions() -> tuple[str, ...]:
        return (
            "Every transfer batch is validated by the canonical normal-transfer legality service.",
            "Future purchases use the current observed FPL price and must be recalculated "
            "before acting.",
            "A missing selling price uses current price only as an optimistic upper bound; "
            "the route is provisional.",
            "The search considers at most three transfers, two Gameweeks and the cheapest "
            "bounded replacement pool.",
            "Players are not ranked by form, fixtures, expected points or any football-"
            "performance forecast.",
        )
