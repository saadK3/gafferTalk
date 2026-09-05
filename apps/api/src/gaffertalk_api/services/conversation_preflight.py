import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from gaffertalk_api.domain.models import FplCatalogue, Money, Player, SquadSnapshot
from gaffertalk_api.domain.recommendation_requests import ConversationOutcome
from gaffertalk_api.domain.transfers import (
    ProposedTransfer,
    TransferLegalityStatus,
    TransferPlanningState,
    TransferRejectionCode,
)
from gaffertalk_api.services.transfer_legality import TransferLegalityService

TARGET_PATTERNS = (
    re.compile(r"\b(?:get|sign|buy)\s+([a-z0-9 .'-]{2,35}?)(?:\s+(?:into|in|for|to)\b|[?!,.]|$)"),
    re.compile(r"\bbring\s+in\s+([a-z0-9 .'-]{2,35}?)(?:\s+(?:for|to)\b|[?!,.]|$)"),
    re.compile(r"\breplace\b.+?\bwith\s+([a-z0-9 .'-]{2,35}?)(?:[?!,.]|$)"),
    re.compile(r"\bswap\b.+?\bfor\s+([a-z0-9 .'-]{2,35}?)(?:[?!,.]|$)"),
    re.compile(
        r"\bis\s+([a-z0-9 .'-]{2,35}?)\s+(?:a|the)\s+"
        r"(?:(?:good|better|best|viable)\s+)?replacement\b"
    ),
    re.compile(
        r"\b(?:afford|fund|finance|funding)\s+(?:for\s+|to\s+)?"
        r"([a-z0-9 .'-]{2,35}?)(?:[?!,.]|$)"
    ),
    re.compile(
        r"\b(?:budget|money)\b.+?\b(?:for|to)\s+(?:bring\s+in\s+|buy\s+|get\s+)?"
        r"([a-z0-9 .'-]{2,35}?)(?:[?!,.]|$)"
    ),
    re.compile(
        r"\b(?:free\s+up|release\s+budget|raise(?:\s+\w+){0,3}\s+money)\s+"
        r"(?:budget\s+)?(?:for\s+|to\s+)?(?:bring\s+in\s+|buy\s+|get\s+)?"
        r"([a-z0-9 .'-]{2,35}?)(?:[?!,.]|$)"
    ),
    re.compile(r"\bwhat\s+about\s+([a-z0-9 .'-]{2,35}?)(?:[?!,.]|$)"),
)


@dataclass(frozen=True)
class ConversationPreflightResult:
    outcome: ConversationOutcome | None = None
    target: Player | None = None
    message: str | None = None
    suggested_outgoing: Player | None = None

    @property
    def can_recommend(self) -> bool:
        return self.outcome is None


class ConversationPreflightService:
    """Resolve explicit player targets and reject impossible requests before Groq."""

    def __init__(self, legality: TransferLegalityService | None = None) -> None:
        self._legality = legality or TransferLegalityService()

    def validate(
        self,
        *,
        question: str,
        outgoing_player_id: int,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        state: TransferPlanningState,
    ) -> ConversationPreflightResult:
        target, attempted_name = self._resolve_target(
            question,
            catalogue,
            excluded_player_id=outgoing_player_id,
        )
        if target is None:
            if attempted_name is not None:
                return ConversationPreflightResult(
                    outcome=ConversationOutcome.TARGET_NOT_FOUND,
                    message=(
                        f"I could not match “{attempted_name}” to a current FPL player. "
                        "Check the spelling and try again. This did not use a Free question."
                    ),
                )
            return ConversationPreflightResult()

        squad_ids = {pick.player.id for pick in snapshot.picks}
        outgoing = catalogue.players[outgoing_player_id]
        if target.id in squad_ids:
            return ConversationPreflightResult(
                outcome=ConversationOutcome.ALREADY_OWNED,
                target=target,
                message=(
                    f"{target.web_name} is already in your current squad, so no transfer is "
                    "required. This did not use a Free question."
                ),
            )
        if target.position is not outgoing.position:
            return ConversationPreflightResult(
                outcome=ConversationOutcome.POSITION_MISMATCH,
                target=target,
                message=(
                    f"{outgoing.web_name} is a {outgoing.position.value}, while "
                    f"{target.web_name} is a {target.position.value}. A one-player FPL transfer "
                    f"must preserve position, so select one of your {target.position.value} "
                    "players to sell. This did not use a Free question."
                ),
            )
        if target.status != "a":
            return ConversationPreflightResult(
                outcome=ConversationOutcome.TARGET_UNAVAILABLE,
                target=target,
                message=(
                    f"{target.web_name} is not currently marked available by FPL, so GafferTalk "
                    "will not recommend this move. This did not use a Free question."
                ),
            )

        legality = self._legality.validate(
            snapshot=snapshot,
            catalogue=catalogue,
            state=state,
            transfers=(
                ProposedTransfer(
                    outgoing_player_id=outgoing_player_id,
                    incoming_player_id=target.id,
                ),
            ),
        )
        if legality.status is TransferLegalityStatus.LEGAL:
            return ConversationPreflightResult(target=target)

        codes = {rejection.code for rejection in legality.rejections}
        if TransferRejectionCode.INSUFFICIENT_FUNDS in codes:
            assert state.bank is not None
            selling_price = state.selling_prices[outgoing_player_id]
            shortfall = target.current_price.tenths - state.bank.tenths - selling_price.tenths
            reason = f"You are £{shortfall / 10:.1f}m short of this transfer."
        elif TransferRejectionCode.CLUB_LIMIT in codes:
            reason = f"This move would exceed FPL’s three-player limit for {target.club.name}."
        else:
            reason = legality.rejections[0].detail
        return ConversationPreflightResult(
            outcome=ConversationOutcome.TARGET_ILLEGAL,
            target=target,
            message=f"{reason} This did not use a Free question.",
        )

    def discover_route(
        self,
        *,
        question: str,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        bank_tenths: int,
        free_transfers: int,
    ) -> ConversationPreflightResult:
        """Find the lowest-sacrifice plausible one-transfer route to an explicit target."""

        target, attempted_name = self._resolve_target(question, catalogue, excluded_player_id=0)
        if target is None:
            if attempted_name is not None:
                return ConversationPreflightResult(
                    outcome=ConversationOutcome.TARGET_NOT_FOUND,
                    message=(
                        f"I could not match “{attempted_name}” to a current FPL player. "
                        "Check the spelling and try again. This did not use a Free question."
                    ),
                )
            return ConversationPreflightResult(
                outcome=ConversationOutcome.TARGET_REQUIRED,
                message=(
                    "Name the player you want to bring in—for example, “What is the best way "
                    "to get Ødegaard into my squad?” This did not use a Free question."
                ),
            )

        squad_ids = {pick.player.id for pick in snapshot.picks}
        if target.id in squad_ids:
            return ConversationPreflightResult(
                outcome=ConversationOutcome.ALREADY_OWNED,
                target=target,
                message=(
                    f"{target.web_name} is already in your current squad, so no transfer is "
                    "required. This did not use a Free question."
                ),
            )
        if target.status != "a":
            return ConversationPreflightResult(
                outcome=ConversationOutcome.TARGET_UNAVAILABLE,
                target=target,
                message=(
                    f"{target.web_name} is not currently marked available by FPL, so GafferTalk "
                    "will not recommend this move. This did not use a Free question."
                ),
            )

        plausible: list[Player] = []
        for pick in snapshot.picks:
            outgoing = pick.player
            if outgoing.position is not target.position:
                continue
            state = TransferPlanningState(
                bank=Money(tenths=bank_tenths),
                free_transfers=free_transfers,
                selling_prices={outgoing.id: outgoing.current_price},
            )
            legality = self._legality.validate(
                snapshot=snapshot,
                catalogue=catalogue,
                state=state,
                transfers=(
                    ProposedTransfer(
                        outgoing_player_id=outgoing.id,
                        incoming_player_id=target.id,
                    ),
                ),
            )
            if legality.status is TransferLegalityStatus.LEGAL:
                plausible.append(outgoing)

        if not plausible:
            return ConversationPreflightResult(
                outcome=ConversationOutcome.TARGET_ILLEGAL,
                target=target,
                message=(
                    f"There is no plausible legal one-transfer route to {target.web_name} using "
                    "your bank and current public prices. A multi-transfer route is outside the "
                    "Free planner. This did not use a Free question."
                ),
            )

        suggested = min(
            plausible,
            key=lambda player: (
                player.total_points,
                player.expected_goals + player.expected_assists,
                player.selected_by_percent,
                player.id,
            ),
        )
        return ConversationPreflightResult(
            outcome=ConversationOutcome.SELLING_PRICE_REQUIRED,
            target=target,
            suggested_outgoing=suggested,
            message=(
                f"The lowest-sacrifice plausible route is {suggested.web_name} → "
                f"{target.web_name}. Confirm {suggested.web_name}’s actual selling price from FPL "
                "before I run the final check. The public "
                f"£{suggested.current_price.tenths / 10:.1f}m "
                "price is only a ceiling; no Free question was used."
            ),
        )

    @classmethod
    def _resolve_target(
        cls,
        question: str,
        catalogue: FplCatalogue,
        *,
        excluded_player_id: int,
    ) -> tuple[Player | None, str | None]:
        normalized_question = cls._normalize(question)
        candidates = tuple(
            player for player in catalogue.players.values() if player.id != excluded_player_id
        )
        attempted_name = cls._extract_attempted_target(normalized_question)
        if attempted_name is not None:
            exact = [
                player for player in candidates if attempted_name in cls._player_aliases(player)
            ]
            if len(exact) == 1:
                return exact[0], None
            if len(exact) > 1:
                return None, attempted_name

            embedded = [
                player
                for player in candidates
                if any(
                    " " in alias and cls._contains_name(attempted_name, alias)
                    for alias in cls._player_aliases(player)
                )
            ]
            if len(embedded) == 1:
                return embedded[0], None
            if len(embedded) > 1:
                return None, attempted_name

            ranked = sorted(
                [
                    (
                        max(
                            SequenceMatcher(
                                None,
                                attempted_name.replace(" ", ""),
                                alias.replace(" ", ""),
                            ).ratio()
                            for alias in cls._player_aliases(player)
                        ),
                        player,
                    )
                    for player in candidates
                ],
                key=lambda item: item[0],
            )
            best_score, best_player = ranked[-1]
            second_score = ranked[-2][0] if len(ranked) > 1 else 0.0
            if best_score >= 0.78 and best_score - second_score >= 0.04:
                return best_player, None
            return None, attempted_name

        return None, None

    @classmethod
    def _player_aliases(cls, player: Player) -> set[str]:
        aliases = {cls._normalize(player.web_name)}
        full_name = cls._normalize(f"{player.first_name} {player.second_name}")
        second_name = cls._normalize(player.second_name)
        if full_name:
            aliases.add(full_name)
        if second_name:
            aliases.add(second_name)
        return aliases

    @staticmethod
    def _extract_attempted_target(question: str) -> str | None:
        for pattern in TARGET_PATTERNS:
            match = pattern.search(question)
            if match:
                value = match.group(1).strip(" .'-")
                return value or None
        return None

    @staticmethod
    def _contains_name(question: str, player_name: str) -> bool:
        return f" {player_name} " in f" {question} "

    @staticmethod
    def _normalize(value: str) -> str:
        ascii_value = "".join(
            character
            for character in unicodedata.normalize("NFKD", value.casefold())
            if not unicodedata.combining(character)
        )
        return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())
