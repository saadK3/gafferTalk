import re
from dataclasses import dataclass
from datetime import UTC, datetime

from gaffertalk_api.domain.general_research import (
    GeneralResearchReport,
    GeneralResearchRequest,
    GeneralResearchStatus,
    GroundedReason,
    ResearchAlternative,
    ResearchCalculation,
    ResearchCapability,
    ResearchFact,
)
from gaffertalk_api.domain.models import FplCatalogue, Player, Position
from gaffertalk_api.domain.player_evidence import (
    EvidenceNature,
    PlayerEvidence,
    PlayerEvidenceReport,
    PlayerEvidenceRequest,
)
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.fpl.mapper import map_catalogue
from gaffertalk_api.services.conversation_preflight import ConversationPreflightService
from gaffertalk_api.services.player_evidence_loader import PlayerEvidenceLoader

MAX_CANDIDATES = 8

POSITION_PATTERNS: tuple[tuple[Position, tuple[str, ...]], ...] = (
    (Position.GOALKEEPER, ("goalkeeper", "goalkeepers", "gkp", "keeper", "keepers")),
    (Position.DEFENDER, ("defender", "defenders", "def", "defence", "defense")),
    (Position.MIDFIELDER, ("midfielder", "midfielders", "mid", "midfield")),
    (Position.FORWARD, ("forward", "forwards", "fwd", "striker", "strikers")),
)

PRICE_PATTERN = re.compile(
    r"\b(?:under|below|less\s+than|up\s+to|at\s+most|maximum\s+price(?:\s+of)?|budget(?:\s+of)?)"
    r"\s*£?\s*(\d+(?:\.\d+)?)\s*m?\b",
    re.IGNORECASE,
)

SUBJECT_PATTERN = re.compile(
    r"\b(?:alternative|alternatives|replacement|replacements)\s+(?:to|for)\s+"
    r"([a-z0-9 .'-]{2,35}?)(?=\s+(?:with|under|below|who|that|and)\b|[?!,.]|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ParsedAlternativesQuestion:
    subject: Player | None
    position: Position | None
    attempted_subject: str | None
    price_ceiling_tenths: int | None
    comparison: str
    clarification: str | None = None


class HistoricalAlternativesAgent:
    """Compare available players using observed historical output and minutes."""

    def __init__(
        self,
        client: FplClient,
        *,
        clock=lambda: datetime.now(UTC),
        evidence_loader: PlayerEvidenceLoader | None = None,
    ) -> None:
        self._client = client
        self._clock = clock
        self._evidence_loader = evidence_loader or PlayerEvidenceLoader(client, clock=clock)

    async def research(self, request: GeneralResearchRequest) -> GeneralResearchReport:
        bootstrap = await self._client.get_bootstrap_observation()
        catalogue = map_catalogue(bootstrap.value, bootstrap.fetched_at)
        parsed = self._parse_question(request.question, catalogue)
        if parsed.clarification is not None:
            return self._clarification_report(request, parsed.clarification)

        squad_ids = set(request.squad.player_ids) if request.squad is not None else set()
        candidates = self._candidate_pool(
            catalogue=catalogue,
            subject=parsed.subject,
            position=parsed.position,
            squad_ids=squad_ids,
            price_ceiling_tenths=parsed.price_ceiling_tenths,
            comparison=parsed.comparison,
        )
        if not candidates:
            return self._empty_report(request, parsed)

        evidence_ids = tuple(
            dict.fromkeys(
                [
                    *(player.id for player in ([parsed.subject] if parsed.subject else [])),
                    *(player.id for player in candidates),
                ]
            )
        )
        evidence = await self._evidence_loader.load(PlayerEvidenceRequest(player_ids=evidence_ids))
        ranked = self._rank_candidates(
            candidates=candidates,
            evidence=evidence,
            subject=parsed.subject,
            comparison=parsed.comparison,
        )
        selected = ranked[:3]
        recommended = selected[0]
        alternatives = tuple(
            self._alternative(rank, item, evidence)
            for rank, item in enumerate(selected[1:], start=1)
        )
        report_evidence = self._selected_evidence(evidence, selected, parsed.subject)
        recommendation_reason = self._recommendation_reason(
            recommended, parsed, evidence, subject=parsed.subject
        )
        objection = self._strongest_objection(report_evidence, parsed.comparison)
        facts = self._facts(selected, evidence, parsed.subject)
        calculations = self._calculations(selected, evidence, parsed.subject)
        return GeneralResearchReport(
            question=request.question,
            capability=ResearchCapability.HISTORICAL_ALTERNATIVES,
            status=GeneralResearchStatus.RECOMMENDATION,
            subject=parsed.subject,
            recommended_action=(
                f"Use {recommended.web_name} as the leading historical alternative for this "
                "comparison."
            ),
            alternatives=alternatives,
            facts=facts,
            calculations=calculations,
            opinion=(
                f"My view is that {recommended.web_name} is the strongest supported option "
                "among the compared players on the requested historical basis."
            ),
            strongest_objection=objection,
            change_conditions=(
                "Refresh the FPL catalogue and player summaries before the deadline.",
                "A new injury, suspension or role change can make historical comparisons less "
                "relevant.",
            ),
            grounded_reasons=(
                GroundedReason(id="comparison", text=recommendation_reason),
                GroundedReason(
                    id="historical_scope",
                    text=(
                        "Points and minutes are observed historical FPL values; no future "
                        "returns are forecast."
                    ),
                ),
                GroundedReason(id="limitation", text=objection),
            ),
            assumptions=(
                "Points, minutes and starts describe historical FPL observations, not "
                "expected future points.",
                "Recent minutes reliability is calculated from the available per-Gameweek history.",
                f"The comparison screened at most {MAX_CANDIDATES} available candidates before "
                "selecting three to report.",
            ),
            evidence=report_evidence,
            metadata={
                "position": parsed.position.value if parsed.position else None,
                "price_ceiling_tenths": parsed.price_ceiling_tenths,
                "comparison": parsed.comparison,
                "candidate_count": len(candidates),
            },
        )

    @staticmethod
    def _parse_question(question: str, catalogue: FplCatalogue) -> ParsedAlternativesQuestion:
        subject, attempted = ConversationPreflightService._resolve_target(
            question, catalogue, excluded_player_id=0
        )
        if subject is None:
            subject_match = SUBJECT_PATTERN.search(question)
            if subject_match:
                subject, attempted = ConversationPreflightService._resolve_target(
                    f"get {subject_match.group(1)}", catalogue, excluded_player_id=0
                )
        normalized = ConversationPreflightService._normalize(question)
        position = subject.position if subject is not None else None
        if position is None:
            for candidate_position, words in POSITION_PATTERNS:
                if any(re.search(rf"\b{re.escape(word)}s?\b", normalized) for word in words):
                    position = candidate_position
                    break
        if position is None:
            if attempted is not None:
                return ParsedAlternativesQuestion(
                    subject=None,
                    position=None,
                    attempted_subject=attempted,
                    price_ceiling_tenths=None,
                    comparison="balanced",
                    clarification=(
                        f"I could not match “{attempted}” to a current FPL player. Check the "
                        "spelling or name a position to compare."
                    ),
                )
            return ParsedAlternativesQuestion(
                subject=None,
                position=None,
                attempted_subject=None,
                price_ceiling_tenths=None,
                comparison="balanced",
                clarification=(
                    "Which player or position should I compare? Historical alternatives only "
                    "need a comparison scope; bank and selling prices are not required."
                ),
            )
        price_ceiling = None
        price_match = PRICE_PATTERN.search(question)
        if price_match:
            price_ceiling = round(float(price_match.group(1)) * 10)
        if any(
            word in normalized
            for word in (
                "minute",
                "minutes",
                "starts",
                "starter",
                "starters",
                "reliable",
                "consistent",
            )
        ):
            comparison = "minutes"
        elif any(
            word in normalized
            for word in ("point", "points", "output", "returns", "goals", "assists")
        ):
            comparison = "points"
        else:
            comparison = "balanced"
        return ParsedAlternativesQuestion(
            subject=subject,
            position=position,
            attempted_subject=attempted,
            price_ceiling_tenths=price_ceiling,
            comparison=comparison,
        )

    @staticmethod
    def _candidate_pool(
        *,
        catalogue: FplCatalogue,
        subject: Player | None,
        position: Position | None,
        squad_ids: set[int],
        price_ceiling_tenths: int | None,
        comparison: str,
    ) -> tuple[Player, ...]:
        assert position is not None
        eligible = [
            player
            for player in catalogue.players.values()
            if player.position is position
            and player.status == "a"
            and player.id not in squad_ids
            and (subject is None or player.id != subject.id)
            and (
                price_ceiling_tenths is None or player.current_price.tenths <= price_ceiling_tenths
            )
        ]
        if subject is not None and comparison == "balanced":
            eligible.sort(
                key=lambda player: (
                    abs(player.total_points - subject.total_points),
                    -player.minutes,
                    -player.starts,
                    player.id,
                )
            )
        elif comparison == "minutes":
            eligible.sort(
                key=lambda player: (
                    -(player.minutes / max(player.starts, 1)),
                    -player.starts,
                    -player.total_points,
                    player.id,
                )
            )
        else:
            eligible.sort(key=lambda player: (-player.total_points, -player.minutes, player.id))
        return tuple(eligible[:MAX_CANDIDATES])

    @classmethod
    def _rank_candidates(
        cls,
        *,
        candidates: tuple[Player, ...],
        evidence: PlayerEvidenceReport,
        subject: Player | None,
        comparison: str,
    ) -> tuple[Player, ...]:
        evidence_by_id = {item.player_id: item for item in evidence.players}
        subject_evidence = evidence_by_id.get(subject.id) if subject else None
        subject_reliability = cls._minutes_reliability(subject_evidence)

        def key(player: Player) -> tuple[float, ...]:
            item = evidence_by_id.get(player.id)
            reliability = cls._minutes_reliability(item)
            recent_starts = cls._recent_starts(item)
            similarity = abs(player.total_points - subject.total_points) if subject else 0
            if subject is not None and comparison == "minutes":
                return (
                    0 if reliability > subject_reliability else 1,
                    -reliability,
                    similarity,
                    -recent_starts,
                    -player.total_points,
                    player.id,
                )
            if subject is not None and comparison == "balanced":
                return (
                    similarity,
                    -reliability,
                    -recent_starts,
                    -player.total_points,
                    player.id,
                )
            if comparison == "minutes":
                return (-reliability, -recent_starts, -player.total_points, player.id)
            return (-player.total_points, -reliability, -recent_starts, player.id)

        return tuple(sorted(candidates, key=key))

    @staticmethod
    def _alternative(
        rank: int, player: Player, evidence: PlayerEvidenceReport
    ) -> ResearchAlternative:
        return ResearchAlternative(
            rank=rank,
            player=player,
            action=f"Compare {player.web_name} as an alternative.",
            reason=(
                f"{player.web_name} has {player.total_points} historical FPL points, "
                f"{player.minutes} minutes and {player.starts} starts."
            ),
            facts=HistoricalAlternativesAgent._player_facts(player, evidence),
        )

    @staticmethod
    def _selected_evidence(
        evidence: PlayerEvidenceReport,
        selected: tuple[Player, ...],
        subject: Player | None,
    ) -> PlayerEvidenceReport:
        selected_ids = {player.id for player in selected}
        if subject is not None:
            selected_ids.add(subject.id)
        return evidence.model_copy(
            update={
                "players": tuple(
                    item for item in evidence.players if item.player_id in selected_ids
                )
            }
        )

    @staticmethod
    def _facts(
        selected: tuple[Player, ...],
        evidence: PlayerEvidenceReport,
        subject: Player | None,
    ) -> tuple[ResearchFact, ...]:
        facts: list[ResearchFact] = []
        players = (*selected, *((subject,) if subject is not None else ()))
        for player in dict.fromkeys(players):
            facts.extend(HistoricalAlternativesAgent._player_facts(player, evidence))
        return tuple(facts)

    @staticmethod
    def _player_facts(player: Player, evidence: PlayerEvidenceReport) -> tuple[ResearchFact, ...]:
        item = next(
            (candidate for candidate in evidence.players if candidate.player_id == player.id),
            None,
        )
        recent_minutes = HistoricalAlternativesAgent._recent_minutes(item)
        recent_starts = HistoricalAlternativesAgent._recent_starts(item)
        reliability = HistoricalAlternativesAgent._minutes_reliability(item)
        return (
            ResearchFact(
                subject=player.web_name,
                label="season_points",
                value=str(player.total_points),
                nature=EvidenceNature.OBSERVED,
                source="official_fpl:bootstrap-static/",
            ),
            ResearchFact(
                subject=player.web_name,
                label="season_minutes",
                value=str(player.minutes),
                nature=EvidenceNature.OBSERVED,
                source="official_fpl:bootstrap-static/",
            ),
            ResearchFact(
                subject=player.web_name,
                label="season_starts",
                value=str(player.starts),
                nature=EvidenceNature.OBSERVED,
                source="official_fpl:bootstrap-static/",
            ),
            ResearchFact(
                subject=player.web_name,
                label="recent_minutes",
                value=str(recent_minutes),
                nature=EvidenceNature.OBSERVED,
                source="official_fpl:element-summary/",
            ),
            ResearchFact(
                subject=player.web_name,
                label="recent_starts",
                value=str(recent_starts),
                nature=EvidenceNature.OBSERVED,
                source="official_fpl:element-summary/",
            ),
            ResearchFact(
                subject=player.web_name,
                label="recent_minutes_reliability",
                value=f"{reliability:.0%}",
                nature=EvidenceNature.CALCULATED,
                source="agent comparison policy 1.0",
            ),
        )

    @staticmethod
    def _calculations(
        selected: tuple[Player, ...],
        evidence: PlayerEvidenceReport,
        subject: Player | None,
    ) -> tuple[ResearchCalculation, ...]:
        calculations: list[ResearchCalculation] = []
        if subject is not None:
            for player in selected:
                if player.id == subject.id:
                    continue
                calculations.append(
                    ResearchCalculation(
                        label=f"{player.web_name} points difference from {subject.web_name}",
                        value=str(player.total_points - subject.total_points),
                        formula="candidate season points - subject season points",
                    )
                )
        for player in selected:
            item = next(
                (candidate for candidate in evidence.players if candidate.player_id == player.id),
                None,
            )
            calculations.append(
                ResearchCalculation(
                    label=f"{player.web_name} recent minutes reliability",
                    value=f"{HistoricalAlternativesAgent._minutes_reliability(item):.0%}",
                    formula="recent minutes / (recent starts × 90)",
                )
            )
        return tuple(calculations)

    @staticmethod
    def _recommendation_reason(
        player: Player,
        parsed: ParsedAlternativesQuestion,
        evidence: PlayerEvidenceReport,
        *,
        subject: Player | None,
    ) -> str:
        item = next(
            (candidate for candidate in evidence.players if candidate.player_id == player.id), None
        )
        reliability = HistoricalAlternativesAgent._minutes_reliability(item)
        if parsed.comparison == "minutes":
            basis = (
                f"the strongest recent minutes reliability in the compared set ({reliability:.0%})"
            )
        elif parsed.comparison == "points":
            basis = (
                f"the highest observed season total in the compared set "
                f"({player.total_points} points)"
            )
        elif subject is not None:
            basis = (
                f"the closest observed season total to {subject.web_name} while retaining "
                f"{reliability:.0%} recent minutes reliability"
            )
        else:
            basis = (
                f"the strongest combination of observed season points ({player.total_points}) "
                f"and {reliability:.0%} recent minutes reliability"
            )
        return f"{player.web_name} leads because of {basis}."

    @staticmethod
    def _strongest_objection(evidence: PlayerEvidenceReport, comparison: str) -> str:
        partial = [item.web_name for item in evidence.players if item.missing_fields]
        if partial:
            return (
                "The strongest objection is incomplete recent evidence for "
                + ", ".join(partial)
                + "; the comparison should be refreshed before relying on it."
            )
        if evidence.freshness.value == "stale":
            return "The strongest objection is that the FPL evidence is stale."
        return (
            f"The strongest objection is that historical {comparison} evidence cannot establish "
            "future points, minutes or selection."
        )

    @staticmethod
    def _recent_minutes(item: PlayerEvidence | None) -> int:
        if item is None or item.recent_history is None:
            return 0
        return item.recent_history.expected_involvement.minutes_denominator or 0

    @staticmethod
    def _recent_starts(item: PlayerEvidence | None) -> int:
        if item is None or item.recent_history is None:
            return 0
        return sum(gameweek.total_starts or 0 for gameweek in item.recent_history.gameweeks)

    @staticmethod
    def _minutes_reliability(item: PlayerEvidence | None) -> float:
        starts = HistoricalAlternativesAgent._recent_starts(item)
        if starts == 0:
            return 0.0
        return min(1.0, HistoricalAlternativesAgent._recent_minutes(item) / (starts * 90))

    @staticmethod
    def _clarification_report(
        request: GeneralResearchRequest, message: str
    ) -> GeneralResearchReport:
        return GeneralResearchReport(
            question=request.question,
            capability=ResearchCapability.HISTORICAL_ALTERNATIVES,
            status=GeneralResearchStatus.NEEDS_CLARIFICATION,
            recommended_action=message,
            facts=(
                ResearchFact(
                    subject="question",
                    label="missing_scope",
                    value=message,
                    nature=EvidenceNature.CALCULATED,
                    source="agent preflight policy 1.0",
                ),
            ),
            opinion=message,
            strongest_objection="No comparison was run until the missing scope is supplied.",
            change_conditions=("Provide a player or position and rerun the comparison.",),
            clarification_question=message,
            grounded_reasons=(
                GroundedReason(
                    id="clarification",
                    text=message,
                ),
            ),
            assumptions=(
                "No external FPL data was fetched because the comparison scope is missing.",
            ),
        )

    @staticmethod
    def _empty_report(
        request: GeneralResearchRequest, parsed: ParsedAlternativesQuestion
    ) -> GeneralResearchReport:
        message = (
            "No currently available players matched the requested position and price constraints."
        )
        return GeneralResearchReport(
            question=request.question,
            capability=ResearchCapability.HISTORICAL_ALTERNATIVES,
            status=GeneralResearchStatus.INFORMATION,
            subject=parsed.subject,
            recommended_action=message,
            facts=(
                ResearchFact(
                    subject="comparison",
                    label="candidate_count",
                    value="0",
                    nature=EvidenceNature.CALCULATED,
                    source="agent comparison policy 1.0",
                ),
            ),
            opinion=message,
            strongest_objection="The catalogue may change; refresh before treating this as final.",
            change_conditions=("Refresh the FPL catalogue and try again.",),
            grounded_reasons=(
                GroundedReason(
                    id="no_candidates",
                    text=message,
                ),
            ),
            assumptions=("Only currently available FPL players were considered.",),
        )
