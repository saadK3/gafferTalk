import json

import httpx
from pydantic import ValidationError

from gaffertalk_api.domain.agent_research import (
    NamedTargetResearchReport,
    NamedTargetSynthesisSelection,
)
from gaffertalk_api.domain.conversation import TransferIntent
from gaffertalk_api.domain.general_research import (
    GeneralResearchReport,
    GeneralSynthesisSelection,
)
from gaffertalk_api.domain.models import Player
from gaffertalk_api.domain.pro_research import (
    ProDecisionReport,
    ProSynthesisSelection,
    SquadActionReport,
    SquadActionSynthesisSelection,
)
from gaffertalk_api.domain.recommendations import RecommendationResult
from gaffertalk_api.domain.route_research import RouteResearchReport, RouteSynthesisSelection


class GroqConversationClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def interpret(
        self, question: str, squad: tuple[Player, ...], selected_outgoing_id: int
    ) -> TransferIntent:
        roster = [{"id": player.id, "name": player.web_name} for player in squad]
        content = await self._completion(
            system=(
                "You interpret an FPL manager's transfer question. The UI has already selected "
                "the outgoing player. Return JSON only with that exact outgoing_player_id, one "
                "strategy (balanced, fixture_first, or value_first), and a short interpretation "
                "of the manager's priorities. Use fixture_first for immediate fixture emphasis, "
                "value_first for savings/value emphasis, and balanced otherwise. Never invent a "
                "player or ID."
            ),
            user=json.dumps(
                {
                    "question": question,
                    "selected_outgoing_player_id": selected_outgoing_id,
                    "squad": roster,
                }
            ),
        )
        try:
            intent = TransferIntent.model_validate_json(content)
        except ValidationError as error:
            raise ValueError("Groq returned an invalid transfer interpretation") from error
        if intent.outgoing_player_id != selected_outgoing_id:
            raise ValueError("Groq did not preserve the selected outgoing player")
        return intent

    async def explain(self, question: str, result: RecommendationResult) -> str:
        facts = {
            "outgoing": result.outgoing.web_name,
            "recommendations": [
                {
                    "rank": item.rank,
                    "player": item.incoming.web_name,
                    "club": item.incoming.club.short_name,
                    "price_tenths": item.incoming.current_price.tenths,
                    "remaining_bank_tenths": item.remaining_bank.tenths,
                    "score": item.score,
                    "reasons": item.reasons,
                    "trade_off": item.trade_off,
                }
                for item in result.recommendations
            ],
        }
        return await self._completion(
            system=(
                "You are GafferTalk. Answer concisely using only the supplied engine facts. "
                "Use plain text only, with no Markdown formatting. Write two to four short "
                "sentences: name the top option, explain it with at least one supplied reason "
                "or trade-off, and briefly distinguish another option when available. Do not "
                "invent statistics, prices, players, certainty, or transfers. The manager makes "
                "the final call."
            ),
            user=json.dumps({"question": question, "engine_facts": facts}),
            json_mode=False,
        )

    async def synthesize_pro_report(self, question: str, report: ProDecisionReport) -> str:
        """Let the model select emphasis, then render only backend-approved facts."""

        reasons = {reason.id: reason.text for reason in report.grounded_reasons}
        content = await self._completion(
            system=(
                "You select which validated reasons should be emphasized in an FPL decision "
                "summary. Return JSON only with the exact supplied verdict and one to three "
                "reason_ids copied from available_reason_ids. Do not return prose, statistics, "
                "players, prices, fixtures or transfer routes."
            ),
            user=json.dumps(
                {
                    "question": question,
                    "verdict": report.verdict,
                    "available_reason_ids": list(reasons),
                }
            ),
        )
        try:
            selection = ProSynthesisSelection.model_validate_json(content)
        except ValidationError as error:
            raise ValueError("Groq returned an invalid Pro synthesis selection") from error
        if selection.verdict is not report.verdict:
            raise ValueError("Groq changed the deterministic Pro verdict")
        if len(set(selection.reason_ids)) != len(selection.reason_ids):
            raise ValueError("Groq repeated a Pro synthesis reason")
        unknown = set(selection.reason_ids) - set(reasons)
        if unknown:
            raise ValueError("Groq selected a reason absent from the Pro report")
        selected = [
            reasons[reason_id]
            for reason_id in selection.reason_ids
            if reasons[reason_id] != report.recommended_action
        ]
        detail = " ".join(selected)
        agency = (
            " If you still prefer the requested move, the legal route in the report remains valid."
            if report.verdict.value in {"hold", "wait", "avoid"}
            else " Recheck the change conditions before the deadline."
        )
        return f"{report.recommended_action} {detail}{agency}".strip()

    async def synthesize_squad_action_report(self, question: str, report: SquadActionReport) -> str:
        """Render a whole-squad summary from deterministic approved reasons only."""

        reasons = {reason.id: reason.text for reason in report.grounded_reasons}
        content = await self._completion(
            system=(
                "Select emphasis for a validated FPL whole-squad decision. Return JSON only "
                "with the exact supplied status and one to three reason_ids copied from "
                "available_reason_ids. Do not return prose, players, statistics, prices, "
                "fixtures or transfer routes."
            ),
            user=json.dumps(
                {
                    "question": question,
                    "status": report.status,
                    "available_reason_ids": list(reasons),
                }
            ),
        )
        try:
            selection = SquadActionSynthesisSelection.model_validate_json(content)
        except ValidationError as error:
            raise ValueError("Groq returned an invalid squad-action synthesis") from error
        if selection.status is not report.status:
            raise ValueError("Groq changed the deterministic squad-action status")
        if len(set(selection.reason_ids)) != len(selection.reason_ids):
            raise ValueError("Groq repeated a squad-action synthesis reason")
        if set(selection.reason_ids) - set(reasons):
            raise ValueError("Groq selected a reason absent from the squad-action report")
        selected = [
            reasons[reason_id]
            for reason_id in selection.reason_ids
            if reason_id != "recommended_action"
        ]
        detail = " ".join(selected)
        action_text = reasons.get("recommended_action")
        if action_text is None:
            raise ValueError("Squad-action report is missing its approved action reason")
        return f"{action_text} {detail}".strip()

    async def synthesize_route_report(self, question: str, report: RouteResearchReport) -> str:
        """Render a route summary using only deterministic approved reasons."""

        reasons = {reason.id: reason.text for reason in report.grounded_reasons}
        content = await self._completion(
            system=(
                "Select emphasis for a deterministic FPL route report. Return JSON only with "
                "the exact supplied status, exact supplied verdict and one to three reason_ids "
                "copied from available_reason_ids. Do not return prose, players, statistics, "
                "prices, fixtures or transfer routes."
            ),
            user=json.dumps(
                {
                    "question": question,
                    "status": report.status,
                    "verdict": report.verdict,
                    "available_reason_ids": list(reasons),
                }
            ),
        )
        try:
            selection = RouteSynthesisSelection.model_validate_json(content)
        except ValidationError as error:
            raise ValueError("Groq returned an invalid route synthesis") from error
        if selection.status is not report.status or selection.verdict is not report.verdict:
            raise ValueError("Groq changed the deterministic route result")
        if len(set(selection.reason_ids)) != len(selection.reason_ids):
            raise ValueError("Groq repeated a route synthesis reason")
        if set(selection.reason_ids) - set(reasons):
            raise ValueError("Groq selected a reason absent from the route report")
        selected = [reasons[reason_id] for reason_id in selection.reason_ids]
        if "route" not in selection.reason_ids:
            selected.insert(0, reasons["route"])
        return " ".join(dict.fromkeys(selected))

    async def synthesize_named_target_report(
        self, question: str, report: NamedTargetResearchReport
    ) -> str:
        """Render a named-target report without allowing the model to change its facts."""

        reasons = {reason.id: reason.text for reason in report.grounded_reasons}
        content = await self._completion(
            system=(
                "Select emphasis for a validated FPL named-player research report. Return "
                "JSON only with the exact supplied status and one to four reason_ids copied "
                "from available_reason_ids. Do not return players, prices, statistics, "
                "fixtures, routes, predictions or new claims."
            ),
            user=json.dumps(
                {
                    "question": question,
                    "status": report.status,
                    "available_reason_ids": list(reasons),
                }
            ),
        )
        try:
            selection = NamedTargetSynthesisSelection.model_validate_json(content)
        except ValidationError as error:
            raise ValueError("Groq returned an invalid named-target synthesis") from error
        if selection.status is not report.status:
            raise ValueError("Groq changed the named-target research status")
        if len(set(selection.reason_ids)) != len(selection.reason_ids):
            raise ValueError("Groq repeated a named-target synthesis reason")
        unknown = set(selection.reason_ids) - set(reasons)
        if unknown:
            raise ValueError("Groq selected a reason absent from the named-target report")
        selected = [reasons[reason_id] for reason_id in selection.reason_ids]
        if "route" in reasons and "route" not in selection.reason_ids:
            selected.insert(0, reasons["route"])
        return " ".join(dict.fromkeys(selected))

    async def synthesize_general_report(self, question: str, report: GeneralResearchReport) -> str:
        """Render a routed report using only its approved reasons."""

        reasons = {reason.id: reason.text for reason in report.grounded_reasons}
        content = await self._completion(
            system=(
                "Select emphasis for a validated FPL research report. Return JSON only with "
                "the exact supplied status and one to four reason_ids copied from "
                "available_reason_ids. Do not return players, prices, statistics, fixtures, "
                "routes, predictions or new claims."
            ),
            user=json.dumps(
                {
                    "question": question,
                    "capability": report.capability,
                    "status": report.status,
                    "available_reason_ids": list(reasons),
                }
            ),
        )
        try:
            selection = GeneralSynthesisSelection.model_validate_json(content)
        except ValidationError as error:
            raise ValueError("Groq returned an invalid general research synthesis") from error
        if selection.status is not report.status:
            raise ValueError("Groq changed the deterministic general research status")
        if len(set(selection.reason_ids)) != len(selection.reason_ids):
            raise ValueError("Groq repeated a general research reason")
        unknown = set(selection.reason_ids) - set(reasons)
        if unknown:
            raise ValueError("Groq selected a reason absent from the general research report")
        selected = [reasons[reason_id] for reason_id in selection.reason_ids]
        return " ".join(dict.fromkeys(selected))

    async def _completion(self, *, system: str, user: str, json_mode: bool = True) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = await self._client.post("chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("Groq returned an incomplete response") from error
