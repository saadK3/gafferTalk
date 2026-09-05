import re
from collections.abc import Callable
from datetime import UTC, datetime

from gaffertalk_api.domain.agent_research import (
    GroundedReason,
    NamedTargetResearchReport,
    NamedTargetResearchRequest,
)
from gaffertalk_api.domain.general_research import (
    GeneralResearchReport,
    GeneralResearchRequest,
    GeneralResearchResponse,
    GeneralResearchStatus,
    ResearchAlternative,
    ResearchCalculation,
    ResearchCapability,
    ResearchFact,
)
from gaffertalk_api.domain.player_evidence import EvidenceNature
from gaffertalk_api.domain.pro_research import (
    SquadActionCandidate,
    SquadActionKind,
    SquadActionReport,
    SquadActionStatus,
)
from gaffertalk_api.domain.recommendation_requests import SquadActionResearchRequest
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.services.conversation_preflight import ConversationPreflightService
from gaffertalk_api.services.historical_alternatives_agent import HistoricalAlternativesAgent
from gaffertalk_api.services.named_target_agent import NamedTargetAgentService
from gaffertalk_api.services.named_target_agent_loader import NamedTargetAgentLoader
from gaffertalk_api.services.pro_research_loader import ProResearchLoader

ALTERNATIVE_WORDS = (
    "alternative",
    "alternatives",
    "replacement",
    "replacements",
    "compare",
    "similar",
)
BUDGET_WORDS = (
    "afford",
    "fund",
    "funding",
    "finance",
    "free up",
    "free-up",
    "release budget",
    "raise money",
    "budget release",
)
HOLD_WORDS = (
    "hold",
    "keep",
    "keeping",
    "retain",
    "preserve",
    "wait",
    "sell",
    "transfer out",
    "move out",
)
CONCERN_WORDS = (
    "concern",
    "concerns",
    "weakness",
    "weakest",
    "problem",
    "priority",
    "priorities",
    "need attention",
    "needs attention",
    "squad issues",
)
POSITION_WORDS = (
    "goalkeeper",
    "goalkeepers",
    "keeper",
    "keepers",
    "defender",
    "defenders",
    "midfielder",
    "midfielders",
    "forward",
    "forwards",
    "striker",
    "strikers",
)


class GeneralResearchAgent:
    """Route supported questions to deterministic research capabilities."""

    def __init__(
        self,
        client: FplClient,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        named_target_loader: NamedTargetAgentLoader | None = None,
        pro_research_loader: ProResearchLoader | None = None,
        alternatives_agent: HistoricalAlternativesAgent | None = None,
    ) -> None:
        self._clock = clock
        self._named_target_loader = named_target_loader or NamedTargetAgentLoader(
            client, clock=clock
        )
        self._pro_research_loader = pro_research_loader or ProResearchLoader(client, clock=clock)
        self._alternatives_agent = alternatives_agent or HistoricalAlternativesAgent(
            client, clock=clock
        )

    @staticmethod
    def classify(question: str) -> ResearchCapability:
        normalized = ConversationPreflightService._normalize(question)
        if GeneralResearchAgent._contains_any(normalized, CONCERN_WORDS):
            return ResearchCapability.SQUAD_CONCERNS
        if GeneralResearchAgent._contains_any(normalized, ALTERNATIVE_WORDS):
            return ResearchCapability.HISTORICAL_ALTERNATIVES
        if (
            GeneralResearchAgent._contains_any(normalized, BUDGET_WORDS)
            or re.search(r"\b(?:raise|free\s+up|release)\b.*\b(?:money|budget)\b", normalized)
            or re.search(r"\b(?:budget|money)\b.*\b(?:for|to|need|afford)\b", normalized)
        ):
            return ResearchCapability.BUDGET_RELEASE
        if GeneralResearchAgent._contains_any(normalized, HOLD_WORDS):
            return ResearchCapability.HOLD_OR_TRANSFER
        if NamedTargetAgentService.has_named_target_intent(question):
            return ResearchCapability.NAMED_TARGET_TRANSFER
        if GeneralResearchAgent._contains_any(normalized, POSITION_WORDS) and (
            GeneralResearchAgent._contains_any(
                normalized, ("best", "which", "who", "points", "minutes")
            )
        ):
            return ResearchCapability.HISTORICAL_ALTERNATIVES
        return ResearchCapability.UNSUPPORTED

    @staticmethod
    def _contains_any(normalized: str, words: tuple[str, ...]) -> bool:
        return any(re.search(rf"\b{re.escape(word)}\b", normalized) for word in words)

    async def research(self, request: GeneralResearchRequest) -> GeneralResearchReport:
        capability = self.classify(request.question)
        if capability is ResearchCapability.UNSUPPORTED:
            return self._unsupported_report(request)
        if capability is ResearchCapability.HISTORICAL_ALTERNATIVES:
            return await self._alternatives_agent.research(request)
        if request.squad is None:
            return self._state_clarification(request, capability)
        if capability in {
            ResearchCapability.NAMED_TARGET_TRANSFER,
            ResearchCapability.BUDGET_RELEASE,
        }:
            named_request = NamedTargetResearchRequest(
                squad=request.squad,
                selling_prices_tenths=request.selling_prices_tenths,
                protected_player_ids=request.protected_player_ids,
                horizon_gameweeks=request.horizon_gameweeks,
                maximum_points_hit=request.maximum_points_hit,
                question=request.question,
            )
            report = await self._named_target_loader.research(named_request)
            return self._from_named_target(report, capability)

        squad_report = await self._pro_research_loader.squad_action(
            SquadActionResearchRequest(
                squad=request.squad,
                selling_prices_tenths=request.selling_prices_tenths,
                risk_preference=request.risk_preference,
                question=request.question,
            )
        )
        return self._from_squad_action(squad_report, capability, request.question)

    @staticmethod
    def _from_named_target(
        report: NamedTargetResearchReport, capability: ResearchCapability
    ) -> GeneralResearchReport:
        status = {
            "recommendation": GeneralResearchStatus.RECOMMENDATION,
            "needs_selling_prices": GeneralResearchStatus.NEEDS_SELLING_PRICES,
            "needs_clarification": GeneralResearchStatus.NEEDS_CLARIFICATION,
            "target_already_owned": GeneralResearchStatus.INFORMATION,
            "no_legal_route": GeneralResearchStatus.NO_ROUTE,
            "no_route_found_within_bounds": GeneralResearchStatus.NO_ROUTE,
            "unsupported": GeneralResearchStatus.UNSUPPORTED,
        }[report.status.value]
        facts: list[ResearchFact] = []
        if report.target is not None:
            facts.extend(
                (
                    ResearchFact(
                        subject=report.target.web_name,
                        label="current_price",
                        value=f"£{report.target.current_price.tenths / 10:.1f}m",
                        nature=EvidenceNature.OBSERVED,
                        source="official_fpl:bootstrap-static/",
                    ),
                    ResearchFact(
                        subject=report.target.web_name,
                        label="fpl_status",
                        value=report.target.status,
                        nature=EvidenceNature.OBSERVED,
                        source="official_fpl:bootstrap-static/",
                    ),
                )
            )
        calculations: list[ResearchCalculation] = []
        alternatives: list[ResearchAlternative] = []
        route_report = report.route_report
        if route_report is not None:
            calculations.extend(
                (
                    ResearchCalculation(
                        label="planning_horizon",
                        value=", ".join(f"GW{item}" for item in report.horizon_gameweek_ids),
                        formula="requested upcoming Gameweeks",
                    ),
                    ResearchCalculation(
                        label="maximum_points_hit",
                        value=str(report.maximum_points_hit),
                        formula="manager constraint",
                    ),
                )
            )
            for rank, route in enumerate(route_report.alternatives, start=1):
                transfers = ", ".join(
                    f"{step.outgoing.web_name} → {step.incoming.web_name}"
                    for plan_step in route.steps
                    for transfer in plan_step.transfers
                    for step in (transfer,)
                )
                alternatives.append(
                    ResearchAlternative(
                        rank=rank,
                        player=route.target,
                        action=f"Use alternative route {rank}.",
                        reason=(
                            f"Arrives in Gameweek {route.target_arrival_gameweek_id}, uses "
                            f"{route.total_transfers} transfer(s), costs {route.total_points_hit} "
                            f"points and leaves £{route.remaining_bank.tenths / 10:.1f}m; "
                            f"transfers: {transfers or 'roll only'}."
                        ),
                    )
                )
            if route_report.primary_route is not None:
                route = route_report.primary_route
                calculations.extend(
                    (
                        ResearchCalculation(
                            label="recommended_transfers",
                            value=str(route.total_transfers),
                            formula="validated route transfer count",
                        ),
                        ResearchCalculation(
                            label="remaining_bank",
                            value=f"£{route.remaining_bank.tenths / 10:.1f}m",
                            formula="starting bank + selling proceeds - purchase prices - hits",
                        ),
                    )
                )
        return GeneralResearchReport(
            question=report.question,
            capability=capability,
            status=status,
            subject=report.target,
            recommended_action=report.recommendation_reason,
            alternatives=tuple(alternatives[:2]),
            facts=tuple(facts)
            or (
                ResearchFact(
                    subject="research",
                    label="result",
                    value=report.recommendation_reason,
                    nature=EvidenceNature.CALCULATED,
                    source="agent route policy 1.0",
                ),
            ),
            calculations=tuple(calculations),
            opinion=(
                "This is the best-supported route under the supplied constraints; it is a "
                "feasibility opinion, not a forecast."
            ),
            strongest_objection=report.strongest_objection,
            change_conditions=report.change_conditions,
            clarification_question=report.clarification_question,
            grounded_reasons=tuple(
                GroundedReason(id=reason.id, text=reason.text) for reason in report.grounded_reasons
            ),
            assumptions=report.assumptions,
            evidence=report.evidence,
            named_target_report=report,
            route_report=report.route_report,
            metadata={"protected_player_ids": [player.id for player in report.protected_players]},
        )

    @staticmethod
    def _from_squad_action(
        report: SquadActionReport,
        capability: ResearchCapability,
        question: str,
    ) -> GeneralResearchReport:
        status = (
            GeneralResearchStatus.NEEDS_SELLING_PRICES
            if report.status is SquadActionStatus.NEEDS_SELLING_PRICE
            else GeneralResearchStatus.RECOMMENDATION
        )
        lead = report.recommended_action or report.provisional_action
        subject = (
            lead.outgoing
            if lead is not None and lead.outgoing is not None
            else (report.ranked_concerns[0].player if report.ranked_concerns else None)
        )
        alternatives: list[ResearchAlternative] = []
        for action in report.compared_actions:
            if lead is not None and action == lead:
                continue
            if len(alternatives) == 2:
                break
            alternatives.append(
                GeneralResearchAgent._squad_alternative(len(alternatives) + 1, action)
            )
        facts = [
            ResearchFact(
                subject=report.ranked_concerns[0].player.web_name,
                label="leading_squad_concern",
                value=report.priority_explanation,
                nature=EvidenceNature.CALCULATED,
                source="agent squad-priority policy 1.0",
            )
        ]
        calculations = [
            ResearchCalculation(
                label="risk_preference",
                value=report.risk_preference.value,
                formula="manager-selected action policy",
            ),
            ResearchCalculation(
                label="hit_analysis",
                value=report.hit_analysis.comparison,
                formula="policy-adjusted evidence gain versus rolling",
            ),
        ]
        if lead is not None:
            facts.extend(
                (
                    ResearchFact(
                        subject=lead.outgoing.web_name if lead.outgoing else "squad",
                        label="recommended_action",
                        value=lead.explanation,
                        nature=EvidenceNature.CALCULATED,
                        source="agent squad-action policy 1.0",
                    ),
                    ResearchFact(
                        subject=lead.outgoing.web_name if lead.outgoing else "squad",
                        label="points_hit",
                        value=str(lead.points_hit),
                        nature=EvidenceNature.CALCULATED,
                        source="official_fpl transfer rules",
                    ),
                )
            )
        return GeneralResearchReport(
            question=question,
            capability=capability,
            status=status,
            subject=subject,
            recommended_action=(
                lead.explanation if lead is not None else report.priority_explanation
            ),
            alternatives=tuple(alternatives),
            facts=tuple(facts),
            calculations=tuple(calculations),
            opinion=(
                "My view is based on the documented squad-priority policy and the comparison "
                "with rolling; it does not forecast future points."
            ),
            strongest_objection=(
                report.change_conditions[0]
                if report.change_conditions
                else "New FPL information can change the priority order."
            ),
            change_conditions=report.change_conditions,
            grounded_reasons=tuple(
                GroundedReason(id=reason.id, text=reason.text) for reason in report.grounded_reasons
            ),
            assumptions=report.assumptions,
            squad_action_report=report,
            metadata={"risk_preference": report.risk_preference.value},
        )

    @staticmethod
    def _squad_alternative(rank: int, action: SquadActionCandidate) -> ResearchAlternative:
        if action.action is SquadActionKind.ROLL:
            return ResearchAlternative(
                rank=rank,
                action="Roll the transfer.",
                reason=action.explanation,
            )
        assert action.outgoing is not None and action.incoming is not None
        return ResearchAlternative(
            rank=rank,
            player=action.incoming,
            action=f"Transfer {action.outgoing.web_name} to {action.incoming.web_name}.",
            reason=action.explanation,
        )

    def response(
        self, report: GeneralResearchReport, *, assistant_message: str, provider: str, model: str
    ) -> GeneralResearchResponse:
        return GeneralResearchResponse(
            report=report,
            assistant_message=assistant_message,
            provider=provider,
            model=model,
        )

    @staticmethod
    def _state_clarification(
        request: GeneralResearchRequest, capability: ResearchCapability
    ) -> GeneralResearchReport:
        message = (
            "To answer this question I need your current 15-player squad, bank and free "
            "transfers. Those details change transfer legality and opportunity cost."
        )
        return GeneralResearchReport(
            question=request.question,
            capability=capability,
            status=GeneralResearchStatus.NEEDS_CLARIFICATION,
            recommended_action=message,
            facts=(
                ResearchFact(
                    subject="question",
                    label="missing_manager_state",
                    value=message,
                    nature=EvidenceNature.CALCULATED,
                    source="agent preflight policy 1.0",
                ),
            ),
            opinion=message,
            strongest_objection=(
                "No team decision was run without the state that determines legality."
            ),
            change_conditions=("Provide the confirmed squad state and rerun the question.",),
            clarification_question=message,
            grounded_reasons=(GroundedReason(id="clarification", text=message),),
            assumptions=(
                "No external FPL data was fetched because the required private planning state "
                "was not supplied.",
            ),
        )

    @staticmethod
    def _unsupported_report(request: GeneralResearchRequest) -> GeneralResearchReport:
        message = (
            "I can research transfers, historical player alternatives, budget-release routes, "
            "hold-versus-transfer decisions and squad concerns. Ask an FPL question in one of "
            "those areas."
        )
        return GeneralResearchReport(
            question=request.question,
            capability=ResearchCapability.UNSUPPORTED,
            status=GeneralResearchStatus.UNSUPPORTED,
            recommended_action=message,
            facts=(
                ResearchFact(
                    subject="question",
                    label="scope",
                    value=message,
                    nature=EvidenceNature.CALCULATED,
                    source="agent scope policy 1.0",
                ),
            ),
            opinion=message,
            strongest_objection="No FPL research was run because the question is outside scope.",
            change_conditions=("Ask a supported FPL transfer or team-research question.",),
            grounded_reasons=(GroundedReason(id="scope", text=message),),
            assumptions=("No external FPL data was fetched for this response.",),
        )
