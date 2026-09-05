import re
from dataclasses import dataclass
from datetime import datetime

from gaffertalk_api.domain.agent_research import (
    GroundedReason,
    NamedTargetResearchReport,
    NamedTargetResearchRequest,
    NamedTargetResearchStatus,
)
from gaffertalk_api.domain.models import FplCatalogue, Money, Player, SquadSnapshot
from gaffertalk_api.domain.multi_gameweek_planning import (
    MultiGameweekPlanningState,
    MultiGameweekRoute,
    MultiGameweekRouteReport,
    MultiGameweekRouteRequest,
    MultiGameweekSearchStatus,
)
from gaffertalk_api.domain.player_evidence import PlayerEvidenceReport, PlayerEvidenceRequest
from gaffertalk_api.integrations.fpl.client import FplObservation
from gaffertalk_api.integrations.fpl.mapper import map_catalogue
from gaffertalk_api.integrations.fpl.schemas import FplBootstrap, FplFixture
from gaffertalk_api.services.conversation_preflight import ConversationPreflightService
from gaffertalk_api.services.multi_gameweek_routes import MultiGameweekRouteService
from gaffertalk_api.services.player_evidence_loader import PlayerEvidenceLoader
from gaffertalk_api.services.recommendation_loader import RecommendationLoader

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}

HORIZON_PATTERN = re.compile(
    r"\b(?:within|in|over|next)\s+(one|two|1|2)\s+(?:gameweeks?|gws?)\b",
    re.IGNORECASE,
)
HIT_PATTERNS = (
    re.compile(
        r"\b(?:maximum|max(?:imum)?)\s+(?:total\s+)?hits?\s*(?:of\s+)?"
        r"(zero|one|two|three|four|five|six|seven|eight|\d+)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:up\s+to|no\s+more\s+than)\s+(zero|one|two|three|four|five|six|seven|eight|\d+)\s+"
        r"(?:points?\s+)?hits?\b",
        re.IGNORECASE,
    ),
)
PROTECTED_TRIGGERS = (
    "without selling",
    "without sell",
    "not selling",
    "do not sell",
    "don't sell",
    "keep",
    "protect",
)


@dataclass(frozen=True, slots=True)
class ParsedNamedTarget:
    target: Player | None
    attempted_target: str | None
    protected_ids: tuple[int, ...]
    horizon_gameweeks: int
    maximum_points_hit: int
    assumptions: tuple[str, ...]
    clarification: str | None = None
    unsupported: str | None = None


class NamedTargetAgentService:
    """Coordinate validated FPL tools for one bounded named-target question."""

    def __init__(
        self,
        route_service: MultiGameweekRouteService | None = None,
    ) -> None:
        self._route_service = route_service or MultiGameweekRouteService()

    @staticmethod
    def has_named_target_intent(question: str) -> bool:
        return bool(
            re.search(
                r"\b(?:get|bring\s+in|buy|sign|replace|swap|afford|fund|funding|"
                r"free\s+up|release\s+budget|raise\s+money|finance)\b",
                question,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def unsupported_report(
        *, request: NamedTargetResearchRequest, created_at: datetime
    ) -> NamedTargetResearchReport:
        message = (
            "This assistant currently handles named-player transfer questions. "
            "Name the player you want to bring in, for example: “How can I get Haaland?”"
        )
        return NamedTargetAgentService._non_research_report(
            request=request,
            created_at=created_at,
            status=NamedTargetResearchStatus.UNSUPPORTED,
            message=message,
            assumptions=(),
        )

    async def research(
        self,
        *,
        request: NamedTargetResearchRequest,
        bootstrap: FplObservation[FplBootstrap],
        fixtures: FplObservation[tuple[FplFixture, ...]],
        evidence_loader: PlayerEvidenceLoader,
        created_at: datetime,
    ) -> NamedTargetResearchReport:
        catalogue = map_catalogue(bootstrap.value, bootstrap.fetched_at)
        snapshot = RecommendationLoader.build_snapshot(request.squad, catalogue)
        snapshot = snapshot.model_copy(
            update={"gameweek": self._planning_snapshot_gameweek(catalogue)}
        )
        parsed = self._parse_question(request, catalogue, snapshot)
        if parsed.unsupported is not None:
            return self._non_research_report(
                request=request,
                created_at=created_at,
                status=NamedTargetResearchStatus.UNSUPPORTED,
                message=parsed.unsupported,
                assumptions=parsed.assumptions,
            )
        if parsed.clarification is not None:
            return self._non_research_report(
                request=request,
                created_at=created_at,
                status=NamedTargetResearchStatus.NEEDS_CLARIFICATION,
                message=parsed.clarification,
                assumptions=parsed.assumptions,
            )
        assert parsed.target is not None
        horizon = tuple(
            range(snapshot.gameweek.id + 1, snapshot.gameweek.id + parsed.horizon_gameweeks + 1)
        )
        state = MultiGameweekPlanningState(
            snapshot=snapshot,
            bank=Money(tenths=request.squad.bank_tenths),
            free_transfers=request.squad.free_transfers,
            selling_prices={
                player_id: Money(tenths=price)
                for player_id, price in request.selling_prices_tenths.items()
            },
        )
        route_report = self._route_service.search(
            request=MultiGameweekRouteRequest(
                state=state,
                target_player_id=parsed.target.id,
                horizon_gameweek_ids=horizon,
                protected_player_ids=parsed.protected_ids,
                maximum_points_hit=parsed.maximum_points_hit,
            ),
            catalogue=catalogue,
        )
        evidence_ids = self._evidence_ids(route_report)
        evidence = await evidence_loader.load(PlayerEvidenceRequest(player_ids=evidence_ids))
        status = self._status(route_report.status)
        recommended = (
            route_report.primary_route
            if status is NamedTargetResearchStatus.RECOMMENDATION
            else None
        )
        provisional = (
            route_report.primary_route
            if status is NamedTargetResearchStatus.NEEDS_SELLING_PRICES
            else None
        )
        recommendation_reason, alternative_reasons = self._route_reasons(route_report, status)
        objection = self._strongest_objection(route_report, evidence)
        report = NamedTargetResearchReport(
            question=request.question,
            created_at=created_at,
            status=status,
            target=parsed.target,
            protected_players=tuple(
                catalogue.players[player_id] for player_id in parsed.protected_ids
            ),
            horizon_gameweek_ids=horizon,
            maximum_points_hit=parsed.maximum_points_hit,
            route_report=route_report,
            evidence=evidence,
            recommended_route=recommended,
            provisional_route=provisional,
            alternatives=route_report.alternatives,
            recommendation_reason=recommendation_reason,
            alternative_reasons=alternative_reasons,
            strongest_objection=objection,
            change_conditions=(
                "Refresh the FPL data before the deadline; status, news, fixtures and prices "
                "can change.",
                "Reconfirm every outgoing player's selling price before treating the route "
                "as exact.",
                "A material squad, bank or free-transfer change requires this plan to be "
                "recalculated.",
            ),
            grounded_reasons=(
                GroundedReason(id="route", text=recommendation_reason),
                GroundedReason(id="evidence", text=self._evidence_reason(evidence)),
                GroundedReason(id="objection", text=objection),
            ),
            assumptions=parsed.assumptions
            + (
                "The planner searches at most two Gameweeks and three total transfers; it "
                "does not claim global optimality.",
                "The assistant does not forecast future points, minutes, prices or results.",
            ),
        )
        return report

    @staticmethod
    def _parse_question(
        request: NamedTargetResearchRequest,
        catalogue: FplCatalogue,
        snapshot: SquadSnapshot,
    ) -> ParsedNamedTarget:
        target_question = re.split(
            r"\b(?:within|over|next)\s+(?:one|two|1|2)\s+(?:gameweeks?|gws?)\b"
            r"|\bwithout\s+(?:selling|sell)\b"
            r"|\bwith\s+(?:a\s+)?(?:maximum|max|up\s+to|no\s+more\s+than)\b",
            request.question,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        target, attempted = ConversationPreflightService._resolve_target(
            target_question, catalogue, excluded_player_id=0
        )
        assumptions: list[str] = []
        if target is None:
            if attempted is None:
                return ParsedNamedTarget(
                    target=None,
                    attempted_target=None,
                    protected_ids=(),
                    horizon_gameweeks=0,
                    maximum_points_hit=0,
                    assumptions=(),
                    unsupported=(
                        "This assistant currently handles named-player transfer questions. "
                        "Name the player you want to bring in, for example: “How can I get "
                        "Haaland?”"
                    ),
                )
            return ParsedNamedTarget(
                target=None,
                attempted_target=attempted,
                protected_ids=(),
                horizon_gameweeks=0,
                maximum_points_hit=0,
                assumptions=(),
                clarification=(
                    f"I could not match “{attempted}” to a current FPL player. "
                    "Please check the spelling and name the target again."
                ),
            )

        horizon = request.horizon_gameweeks
        if horizon is None:
            match = HORIZON_PATTERN.search(request.question)
            horizon = (
                int(match.group(1))
                if match and match.group(1).isdigit()
                else (NUMBER_WORDS[match.group(1).casefold()] if match else 2)
            )
            if match is None:
                assumptions.append(
                    "No horizon was stated, so the supported default of two upcoming "
                    "Gameweeks was used."
                )
        maximum_hit = request.maximum_points_hit
        if maximum_hit is None:
            maximum_hit = 0
            for pattern in HIT_PATTERNS:
                match = pattern.search(request.question)
                if match:
                    value = match.group(1).casefold()
                    maximum_hit = int(value) if value.isdigit() else NUMBER_WORDS[value]
                    break
            if maximum_hit == 0:
                assumptions.append(
                    "No hit limit was stated, so routes costing more than zero points were "
                    "excluded."
                )
        if maximum_hit % 4:
            return ParsedNamedTarget(
                target=target,
                attempted_target=None,
                protected_ids=(),
                horizon_gameweeks=horizon,
                maximum_points_hit=maximum_hit,
                assumptions=tuple(assumptions),
                clarification=(
                    "FPL hits are charged in four-point steps. Please give a maximum hit of "
                    "0, 4, 8 or another multiple of four."
                ),
            )

        squad_ids = {pick.player.id for pick in snapshot.picks}
        protected = set(request.protected_player_ids)
        normalized_question = ConversationPreflightService._normalize(request.question)
        for player in snapshot.picks:
            aliases = ConversationPreflightService._player_aliases(player.player)
            if any(
                f"{trigger} {alias}" in normalized_question
                for trigger in PROTECTED_TRIGGERS
                for alias in aliases
            ):
                protected.add(player.player.id)
        protected &= squad_ids
        if request.horizon_gameweeks is not None:
            assumptions.append("The requested horizon was supplied as structured manager input.")
        if request.maximum_points_hit is not None:
            assumptions.append("The maximum hit was supplied as structured manager input.")
        return ParsedNamedTarget(
            target=target,
            attempted_target=None,
            protected_ids=tuple(sorted(protected)),
            horizon_gameweeks=horizon,
            maximum_points_hit=maximum_hit,
            assumptions=tuple(assumptions),
        )

    @staticmethod
    def _planning_snapshot_gameweek(catalogue: FplCatalogue):
        current = next((gameweek for gameweek in catalogue.gameweeks if gameweek.is_current), None)
        if current is not None:
            return current
        finished = [gameweek for gameweek in catalogue.gameweeks if gameweek.finished]
        if finished:
            return max(finished, key=lambda gameweek: gameweek.id)
        return min(catalogue.gameweeks, key=lambda gameweek: gameweek.id)

    @staticmethod
    def _status(status: MultiGameweekSearchStatus) -> NamedTargetResearchStatus:
        if status is MultiGameweekSearchStatus.ROUTES:
            return NamedTargetResearchStatus.RECOMMENDATION
        return NamedTargetResearchStatus(status.value)

    @staticmethod
    def _evidence_ids(route_report: MultiGameweekRouteReport) -> tuple[int, ...]:
        ids = {route_report.target.id}
        routes = []
        if route_report.primary_route is not None:
            routes.append(route_report.primary_route)
        routes.extend(route_report.alternatives)
        for route in routes:
            for step in route.steps:
                for transfer in step.transfers:
                    ids.add(transfer.outgoing.id)
                    ids.add(transfer.incoming.id)
        return tuple(sorted(ids))

    @staticmethod
    def _route_reasons(
        route_report: MultiGameweekRouteReport,
        status: NamedTargetResearchStatus,
    ) -> tuple[str, tuple[str, ...]]:
        route = route_report.primary_route
        if status is NamedTargetResearchStatus.NEEDS_SELLING_PRICES and route is not None:
            return (
                f"A provisional route reaches {route.target.web_name} by Gameweek "
                f"{route.target_arrival_gameweek_id}, but exact legality depends on the "
                "missing selling prices listed in the route report.",
                (),
            )
        if status is NamedTargetResearchStatus.RECOMMENDATION and route is not None:
            alternatives = tuple(
                NamedTargetAgentService._compare_route(route, alternative, index)
                for index, alternative in enumerate(route_report.alternatives, start=1)
            )
            return (
                f"Recommended because this is the lowest-hit legal route found under the "
                f"stated bounds: it reaches {route.target.web_name} by Gameweek "
                f"{route.target_arrival_gameweek_id}, uses {route.total_transfers} transfer"
                f"{'s' if route.total_transfers != 1 else ''}, costs "
                f"{route.total_points_hit} points and leaves "
                f"£{route.remaining_bank.tenths / 10:.1f}m.",
                alternatives,
            )
        if status is NamedTargetResearchStatus.TARGET_ALREADY_OWNED:
            return (
                f"No transfer is recommended because {route_report.target.web_name} is "
                "already in the confirmed squad.",
                (),
            )
        if status is NamedTargetResearchStatus.NO_LEGAL_ROUTE:
            return (
                "No legal route exists under the confirmed squad constraints; every possible "
                "player in the target's position is protected or otherwise unavailable.",
                (),
            )
        return (
            "No route was found within the planner's explicit Gameweek, transfer and hit bounds; "
            "this does not prove that no route could ever exist outside those bounds.",
            (),
        )

    @staticmethod
    def _compare_route(
        primary: MultiGameweekRoute,
        alternative: MultiGameweekRoute,
        index: int,
    ) -> str:
        return (
            f"Alternative {index} reaches {alternative.target.web_name} by Gameweek "
            f"{alternative.target_arrival_gameweek_id}, uses {alternative.total_transfers} "
            f"transfer{'s' if alternative.total_transfers != 1 else ''}, costs "
            f"{alternative.total_points_hit} points and leaves "
            f"£{alternative.remaining_bank.tenths / 10:.1f}m; "
            f"the recommended route arrives in Gameweek {primary.target_arrival_gameweek_id} "
            f"with {primary.total_points_hit} points hit and "
            f"£{primary.remaining_bank.tenths / 10:.1f}m remaining."
        )

    @staticmethod
    def _evidence_reason(evidence: PlayerEvidenceReport) -> str:
        observed = sum(player.availability.value == "observed" for player in evidence.players)
        return (
            f"The evidence packet covers {len(evidence.players)} player(s); {observed} are "
            "fully observed. "
            f"Source freshness is {evidence.freshness.value}, and every material fact "
            "remains linked to an FPL endpoint."
        )

    @staticmethod
    def _strongest_objection(
        route_report: MultiGameweekRouteReport,
        evidence: PlayerEvidenceReport,
    ) -> str:
        if evidence.freshness.value == "stale":
            return (
                "The strongest objection is that one or more FPL sources are stale and "
                "should be refreshed before the deadline."
            )
        conflicts = [conflict for player in evidence.players for conflict in player.conflicts]
        if conflicts:
            return (
                "The strongest objection is conflicting fixture information: "
                f"{conflicts[0].message}"
            )
        partial = [player.web_name for player in evidence.players if player.missing_fields]
        if partial:
            return (
                "The strongest objection is incomplete evidence for "
                + ", ".join(partial)
                + "; no forecast should be made from the missing fields."
            )
        if route_report.status is MultiGameweekSearchStatus.NEEDS_SELLING_PRICES:
            return (
                "The strongest objection is that the leading route is provisional until "
                "the relevant outgoing selling prices are confirmed."
            )
        return (
            "The strongest objection is that this is a bounded feasibility decision, not "
            "a prediction of future points or minutes."
        )

    @staticmethod
    def _non_research_report(
        *,
        request: NamedTargetResearchRequest,
        created_at: datetime,
        status: NamedTargetResearchStatus,
        message: str,
        assumptions: tuple[str, ...],
    ) -> NamedTargetResearchReport:
        return NamedTargetResearchReport(
            question=request.question,
            created_at=created_at,
            status=status,
            recommendation_reason=message,
            strongest_objection=(
                "No FPL research was run because the question needs clarification or is "
                "outside this slice's scope."
            ),
            change_conditions=(
                "Ask a supported named-player question to start a bounded research run.",
            ),
            clarification_question=message
            if status is NamedTargetResearchStatus.NEEDS_CLARIFICATION
            else None,
            grounded_reasons=(GroundedReason(id="scope", text=message),),
            assumptions=assumptions or ("No external FPL data was fetched for this response.",),
        )
