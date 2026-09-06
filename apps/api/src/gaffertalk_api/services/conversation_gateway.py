import re
from collections import OrderedDict
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import httpx

from gaffertalk_api.domain.conversation_gateway import (
    ConversationContext,
    ConversationHistory,
    ConversationIntent,
    ConversationIntentStatus,
    ConversationResponse,
    ConversationResponseStatus,
    ConversationTurnRecord,
    ConversationTurnRequest,
    SellingPriceRequest,
)
from gaffertalk_api.domain.general_research import (
    GeneralResearchReport,
    GeneralResearchRequest,
    GeneralResearchResponse,
    GeneralResearchStatus,
    ResearchCapability,
)
from gaffertalk_api.domain.models import Player
from gaffertalk_api.domain.pro_research import RiskPreference
from gaffertalk_api.domain.recommendation_requests import CurrentSquadInput
from gaffertalk_api.services.conversation_preflight import ConversationPreflightService
from gaffertalk_api.services.general_research_agent import GeneralResearchAgent
from gaffertalk_api.services.named_target_agent import PROTECTED_TRIGGERS
from gaffertalk_api.services.player_catalogue import PlayerCatalogueLoader

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
HIT_PATTERN = re.compile(
    r"\b(?:maximum|max(?:imum)?|up\s+to|no\s+more\s+than)\s+"
    r"(?:a\s+)?(?:total\s+)?(?:points?\s+)?hits?\s*(?:of\s*)?"
    r"(?:minus\s*)?(zero|one|two|three|four|five|six|seven|eight|\d+)\b",
    re.IGNORECASE,
)


class ConversationInterpreter(Protocol):
    model: str

    async def interpret_general_question(
        self,
        question: str,
        *,
        squad: tuple[Player, ...],
        history: tuple[dict[str, object], ...],
    ) -> ConversationIntent: ...

    async def synthesize_general_report(
        self, question: str, report: GeneralResearchReport
    ) -> str: ...


class ConversationContextStore:
    """Bounded in-memory context for local and single-instance conversations."""

    def __init__(self, *, max_sessions: int = 100) -> None:
        self._max_sessions = max(1, max_sessions)
        self._contexts: OrderedDict[str, ConversationContext] = OrderedDict()

    def get(self, conversation_id: str) -> ConversationContext | None:
        context = self._contexts.get(conversation_id)
        if context is not None:
            self._contexts.move_to_end(conversation_id)
        return context

    def save(self, context: ConversationContext) -> None:
        self._contexts[context.conversation_id] = context
        self._contexts.move_to_end(context.conversation_id)
        while len(self._contexts) > self._max_sessions:
            self._contexts.popitem(last=False)

    def clear(self, conversation_id: str) -> None:
        self._contexts.pop(conversation_id, None)


class ConversationGateway:
    """Turn flexible user language into a validated GeneralResearchRequest."""

    def __init__(
        self,
        research_agent: GeneralResearchAgent,
        catalogue_loader: PlayerCatalogueLoader,
        *,
        interpreter: ConversationInterpreter | None = None,
        store: ConversationContextStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._research_agent = research_agent
        self._catalogue_loader = catalogue_loader
        self._interpreter = interpreter
        self._store = store or ConversationContextStore()
        self._clock = clock

    async def handle(self, request: ConversationTurnRequest) -> ConversationResponse:
        conversation_id = request.conversation_id or str(uuid4())
        previous = self._store.get(conversation_id)
        squad = request.squad or (previous.squad if previous is not None else None)
        selling_prices = request.selling_prices_tenths or (
            previous.selling_prices_tenths if previous is not None else {}
        )
        risk_preference = request.risk_preference or (
            previous.risk_preference if previous is not None else RiskPreference.BALANCED
        )
        history = previous.history.turns if previous is not None else ()
        squad_players = await self._squad_players(squad)
        intent, interpreter_provider = await self._interpret(
            request.question,
            squad_players=squad_players,
            history=history,
        )
        if (
            intent.target_player_name is None
            and previous is not None
            and intent.capability
            in {
                ResearchCapability.NAMED_TARGET_TRANSFER,
                ResearchCapability.BUDGET_RELEASE,
            }
        ):
            intent = intent.model_copy(update={"target_player_name": previous.target_player_name})
        if request.risk_preference is None and previous is None:
            risk_preference = intent.risk_preference

        protected_ids, protected_error = self._resolve_protected_players(
            intent.protected_player_names,
            squad_players,
            request.protected_player_ids
            or (previous.protected_player_ids if previous is not None else ()),
            question=request.question,
        )
        if protected_error is not None:
            intent = self._clarification_intent(intent, protected_error)
        elif protected_ids:
            resolved_names = tuple(
                player.web_name for player in squad_players if player.id in protected_ids
            )
            intent = intent.model_copy(update={"protected_player_names": resolved_names})

        if intent.status is ConversationIntentStatus.READY:
            intent, state_error = self._validate_ready_state(
                intent,
                squad,
                question=request.question,
                maximum_points_hit=request.maximum_points_hit
                if request.maximum_points_hit is not None
                else (previous.maximum_points_hit if previous is not None else None),
            )
            if state_error is not None:
                intent = self._clarification_intent(intent, state_error)

        context = self._context_after_turn(
            conversation_id=conversation_id,
            previous=previous,
            request=request,
            squad=squad,
            selling_prices=selling_prices,
            risk_preference=risk_preference,
            intent=intent,
            protected_ids=protected_ids,
            history=history,
        )

        if intent.status is ConversationIntentStatus.UNSUPPORTED:
            message = (
                "I can research transfers, historical player alternatives, budget-release "
                "routes, hold-versus-transfer decisions and squad concerns. Ask an FPL "
                "question in one of those areas."
            )
            response = ConversationResponse(
                conversation_id=conversation_id,
                question=request.question,
                status=ConversationResponseStatus.UNSUPPORTED,
                intent=intent,
                assistant_message=message,
                provider="deterministic",
                model="none",
            )
            self._store.save(
                context.model_copy(
                    update={
                        "history": ConversationHistory(
                            turns=(*history, self._record(request, intent, response.status))[-8:]
                        )
                    }
                )
            )
            return response

        if intent.status is ConversationIntentStatus.NEEDS_CLARIFICATION:
            message = intent.clarification_question or intent.explanation
            response = ConversationResponse(
                conversation_id=conversation_id,
                question=request.question,
                status=ConversationResponseStatus.NEEDS_CLARIFICATION,
                intent=intent,
                assistant_message=message,
                provider=interpreter_provider,
                model=self._interpreter.model if self._interpreter is not None else "none",
            )
            self._store.save(
                context.model_copy(
                    update={
                        "history": ConversationHistory(
                            turns=(*history, self._record(request, intent, response.status))[-8:]
                        )
                    }
                )
            )
            return response

        assert intent.capability is not ResearchCapability.UNSUPPORTED
        target_name = intent.target_player_name or (
            previous.target_player_name if previous is not None else None
        )
        research_question = request.question
        if (
            target_name is not None
            and intent.capability
            in {
                ResearchCapability.NAMED_TARGET_TRANSFER,
                ResearchCapability.BUDGET_RELEASE,
            }
            and ConversationPreflightService._normalize(target_name)
            not in ConversationPreflightService._normalize(request.question)
        ):
            research_question = f"{request.question} Bring in {target_name}."
        research_request = GeneralResearchRequest(
            squad=squad,
            selling_prices_tenths=selling_prices,
            risk_preference=risk_preference,
            horizon_gameweeks=intent.horizon_gameweeks
            or request.horizon_gameweeks
            or (previous.horizon_gameweeks if previous is not None else None),
            maximum_points_hit=intent.maximum_points_hit
            if intent.maximum_points_hit is not None
            else request.maximum_points_hit
            if request.maximum_points_hit is not None
            else (previous.maximum_points_hit if previous is not None else None),
            protected_player_ids=protected_ids,
            question=research_question,
        )
        report = await self._research_agent.research(research_request)
        nested, provider, model, message = await self._render(
            request.question,
            report,
        )
        selling_price_requests = self._selling_price_requests(report, squad_players)
        response = ConversationResponse(
            conversation_id=conversation_id,
            question=request.question,
            status=ConversationResponseStatus.ANSWERED,
            intent=intent,
            assistant_message=message,
            research=nested,
            selling_price_requests=selling_price_requests,
            provider=provider,
            model=model,
        )
        self._store.save(
            context.model_copy(
                update={
                    "history": ConversationHistory(
                        turns=(*history, self._record(request, intent, response.status))[-8:]
                    )
                }
            )
        )
        return response

    @staticmethod
    def _selling_price_requests(
        report: GeneralResearchReport,
        squad_players: tuple[Player, ...],
    ) -> tuple[SellingPriceRequest, ...]:
        """Expose missing prices as data the client can render without parsing prose."""

        requested: dict[int, str] = {}
        if report.route_report is not None:
            for player_id in report.route_report.requested_selling_price_player_ids:
                requested[player_id] = (
                    "Confirm this player's actual selling price to validate the proposed route."
                )
        if (
            report.squad_action_report is not None
            and report.squad_action_report.requested_selling_price_for is not None
        ):
            requested_player = report.squad_action_report.requested_selling_price_for
            requested[requested_player.id] = (
                "Confirm this player's actual selling price to validate the leading squad action."
            )

        players_by_id = {player.id: player for player in squad_players}
        if report.route_report is not None:
            routes = (
                report.route_report.primary_route,
                *report.route_report.alternatives,
            )
            for route in routes:
                if route is None:
                    continue
                for step in route.steps:
                    for transfer in step.transfers:
                        players_by_id.setdefault(transfer.outgoing.id, transfer.outgoing)
        requests: list[SellingPriceRequest] = []
        for player_id in sorted(requested):
            matched_player = players_by_id.get(player_id)
            if matched_player is None:
                raise ValueError(
                    f"research report requested an unknown selling-price player: {player_id}"
                )
            requests.append(
                SellingPriceRequest(
                    player_id=matched_player.id,
                    player_name=matched_player.web_name,
                    current_fpl_price_tenths=matched_player.current_price.tenths,
                    reason=requested[player_id],
                )
            )
        return tuple(requests)

    async def _squad_players(self, squad: CurrentSquadInput | None) -> tuple[Player, ...]:
        if squad is None:
            return ()
        catalogue = await self._catalogue_loader.load()
        missing = set(squad.player_ids) - set(catalogue.players)
        if missing:
            missing_ids = ", ".join(str(player_id) for player_id in sorted(missing))
            raise ValueError(f"the confirmed squad contains unknown FPL player IDs: {missing_ids}")
        return tuple(catalogue.players[player_id] for player_id in squad.player_ids)

    async def _interpret(
        self,
        question: str,
        *,
        squad_players: tuple[Player, ...],
        history: tuple[ConversationTurnRecord, ...],
    ) -> tuple[ConversationIntent, str]:
        if self._interpreter is not None:
            try:
                intent = await self._interpreter.interpret_general_question(
                    question,
                    squad=squad_players,
                    history=tuple(record.model_dump(mode="json") for record in history),
                )
                return self._enrich_intent(intent, question), "groq"
            except (httpx.HTTPError, ValueError):
                pass
        return self._enrich_intent(
            self._deterministic_interpret(question), question
        ), "deterministic"

    @staticmethod
    def _enrich_intent(intent: ConversationIntent, question: str) -> ConversationIntent:
        """Recover explicit names and numeric constraints without trusting model extraction."""

        normalized = ConversationPreflightService._normalize(question)
        updates: dict[str, object] = {}
        if intent.target_player_name is None:
            target_text = re.split(
                r"\b(?:within|over|next)\s+(?:one|two|1|2)\s+"
                r"(?:gameweeks?|gws?)\b|\bwith\s+(?:a\s+)?(?:maximum|max|up\s+to|no\s+more\s+than)\b",
                normalized,
                maxsplit=1,
            )[0]
            target_name = ConversationPreflightService._extract_attempted_target(target_text)
            if target_name is not None:
                updates["target_player_name"] = target_name
        if intent.horizon_gameweeks is None:
            match = HORIZON_PATTERN.search(normalized)
            if match is not None:
                value = match.group(1).casefold()
                updates["horizon_gameweeks"] = (
                    int(value) if value.isdigit() else NUMBER_WORDS[value]
                )
        if intent.maximum_points_hit is None:
            match = HIT_PATTERN.search(normalized)
            if match is not None:
                value = match.group(1).casefold()
                updates["maximum_points_hit"] = (
                    int(value) if value.isdigit() else NUMBER_WORDS[value]
                )
        deterministic_capability = GeneralResearchAgent.classify(question)
        if deterministic_capability is not ResearchCapability.UNSUPPORTED and (
            intent.status is ConversationIntentStatus.UNSUPPORTED
            or (
                deterministic_capability
                in {
                    ResearchCapability.NAMED_TARGET_TRANSFER,
                    ResearchCapability.BUDGET_RELEASE,
                }
                and intent.capability
                in {
                    ResearchCapability.HOLD_OR_TRANSFER,
                    ResearchCapability.SQUAD_CONCERNS,
                }
            )
        ):
            updates["capability"] = deterministic_capability
            if intent.status is ConversationIntentStatus.UNSUPPORTED:
                updates.update(
                    {
                        "status": ConversationIntentStatus.READY,
                        "missing_information": (),
                        "clarification_question": None,
                    }
                )
        enriched = intent.model_copy(update=updates) if updates else intent
        if enriched.status is not ConversationIntentStatus.NEEDS_CLARIFICATION:
            return enriched
        remaining = tuple(
            item
            for item in enriched.missing_information
            if not (
                ("target" in item.casefold() and enriched.target_player_name is not None)
                or ("horizon" in item.casefold() and enriched.horizon_gameweeks is not None)
                or ("hit" in item.casefold() and enriched.maximum_points_hit is not None)
            )
        )
        if remaining:
            return enriched.model_copy(update={"missing_information": remaining})
        return enriched.model_copy(
            update={
                "status": ConversationIntentStatus.READY,
                "missing_information": (),
                "clarification_question": None,
                "explanation": "The question contains the information needed to run research.",
            }
        )

    @staticmethod
    def _deterministic_interpret(question: str) -> ConversationIntent:
        capability = GeneralResearchAgent.classify(question)
        target_name = ConversationPreflightService._extract_attempted_target(
            ConversationPreflightService._normalize(question)
        )
        if capability is ResearchCapability.UNSUPPORTED:
            return ConversationIntent(
                capability=capability,
                status=ConversationIntentStatus.UNSUPPORTED,
                explanation="The question is outside the supported FPL research scope.",
            )
        return ConversationIntent(
            capability=capability,
            status=ConversationIntentStatus.READY,
            target_player_name=target_name,
            explanation=f"The question is about {capability.value.replace('_', ' ')}.",
        )

    @staticmethod
    def _resolve_protected_players(
        names: tuple[str, ...],
        squad_players: tuple[Player, ...],
        supplied_ids: tuple[int, ...],
        *,
        question: str,
    ) -> tuple[tuple[int, ...], str | None]:
        protected = set(supplied_ids)
        normalized_question = ConversationPreflightService._normalize(question)
        for player in squad_players:
            aliases = ConversationPreflightService._player_aliases(player)
            if any(
                f"{ConversationPreflightService._normalize(trigger)} {alias}" in normalized_question
                for trigger in PROTECTED_TRIGGERS
                for alias in aliases
            ):
                protected.add(player.id)
        for name in names:
            normalized = ConversationPreflightService._normalize(name)
            matches = [
                player
                for player in squad_players
                if normalized in ConversationPreflightService._player_aliases(player)
            ]
            if len(matches) != 1:
                return (), f"I could not match the protected player “{name}” to your squad."
            protected.add(matches[0].id)
        return tuple(sorted(protected)), None

    @staticmethod
    def _validate_ready_state(
        intent: ConversationIntent,
        squad: CurrentSquadInput | None,
        *,
        question: str,
        maximum_points_hit: int | None,
    ) -> tuple[ConversationIntent, str | None]:
        needs_squad = intent.capability in {
            ResearchCapability.NAMED_TARGET_TRANSFER,
            ResearchCapability.BUDGET_RELEASE,
            ResearchCapability.HOLD_OR_TRANSFER,
            ResearchCapability.SQUAD_CONCERNS,
        }
        if needs_squad and squad is None:
            return intent, (
                "Please provide or load your current 15-player squad, bank and free transfers "
                "so I can check this legally."
            )
        if (
            intent.capability
            in {
                ResearchCapability.NAMED_TARGET_TRANSFER,
                ResearchCapability.BUDGET_RELEASE,
            }
            and not intent.target_player_name
        ):
            return intent, "Which player are you trying to bring into the squad?"
        if (
            intent.capability
            in {
                ResearchCapability.NAMED_TARGET_TRANSFER,
                ResearchCapability.BUDGET_RELEASE,
            }
            and intent.maximum_points_hit is None
            and maximum_points_hit is None
            and re.search(
                r"\b(?:within|over|next)\s+(?:two|three|four|five|2|3|4|5)\s+"
                r"(?:gameweeks?|gws?)\b",
                ConversationPreflightService._normalize(question),
            )
        ):
            return intent, (
                "How many points are you willing to spend on transfer hits for that time window? "
                "Use 0, 4, 8 or another multiple of four."
            )
        return intent, None

    @staticmethod
    def _clarification_intent(intent: ConversationIntent, message: str) -> ConversationIntent:
        return intent.model_copy(
            update={
                "status": ConversationIntentStatus.NEEDS_CLARIFICATION,
                "missing_information": (*intent.missing_information, message),
                "clarification_question": message,
            }
        )

    def _context_after_turn(
        self,
        *,
        conversation_id: str,
        previous: ConversationContext | None,
        request: ConversationTurnRequest,
        squad,
        selling_prices: Mapping[int, int],
        risk_preference: RiskPreference,
        intent: ConversationIntent,
        protected_ids: tuple[int, ...],
        history: tuple[ConversationTurnRecord, ...],
    ) -> ConversationContext:
        return ConversationContext(
            conversation_id=conversation_id,
            squad=squad,
            selling_prices_tenths=dict(selling_prices),
            target_player_name=(
                intent.target_player_name
                or (previous.target_player_name if previous is not None else None)
            ),
            risk_preference=risk_preference,
            horizon_gameweeks=(
                intent.horizon_gameweeks
                or request.horizon_gameweeks
                or (previous.horizon_gameweeks if previous is not None else None)
            ),
            maximum_points_hit=(
                intent.maximum_points_hit
                if intent.maximum_points_hit is not None
                else request.maximum_points_hit
                if request.maximum_points_hit is not None
                else (previous.maximum_points_hit if previous is not None else None)
            ),
            protected_player_ids=protected_ids,
            history=ConversationHistory(turns=history),
        )

    async def _render(
        self, question: str, report: GeneralResearchReport
    ) -> tuple[GeneralResearchResponse, str, str, str]:
        if report.status is not GeneralResearchStatus.RECOMMENDATION:
            message = report.recommended_action
            return (
                self._research_agent.response(
                    report, assistant_message=message, provider="deterministic", model="none"
                ),
                "deterministic",
                "none",
                message,
            )
        if self._interpreter is not None:
            try:
                message = await self._interpreter.synthesize_general_report(question, report)
                return (
                    self._research_agent.response(
                        report,
                        assistant_message=message,
                        provider="groq",
                        model=self._interpreter.model,
                    ),
                    "groq",
                    self._interpreter.model,
                    message,
                )
            except (httpx.HTTPError, ValueError, AttributeError):
                pass
        message = self._deterministic_message(report)
        return (
            self._research_agent.response(
                report, assistant_message=message, provider="deterministic", model="none"
            ),
            "deterministic",
            "none",
            message,
        )

    @staticmethod
    def _deterministic_message(report: GeneralResearchReport) -> str:
        """Keep the local experience useful even when the explanation model is unavailable."""

        parts = [report.recommended_action]
        if report.alternatives:
            parts.append(
                "Alternatives: "
                + "; ".join(
                    f"{alternative.rank}) {alternative.action}"
                    for alternative in report.alternatives
                )
            )
        if report.strongest_objection not in parts:
            parts.append(f"Strongest objection: {report.strongest_objection}")
        return " ".join(parts)

    @staticmethod
    def _record(
        request: ConversationTurnRequest,
        intent: ConversationIntent,
        status: ConversationResponseStatus,
    ) -> ConversationTurnRecord:
        return ConversationTurnRecord(
            question=request.question,
            intent=intent,
            response_status=status,
        )
