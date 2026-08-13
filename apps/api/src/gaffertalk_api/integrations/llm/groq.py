import json

import httpx
from pydantic import ValidationError

from gaffertalk_api.domain.conversation import TransferIntent
from gaffertalk_api.domain.models import Player
from gaffertalk_api.domain.recommendations import RecommendationResult


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
                "the outgoing player. Return JSON only with that exact outgoing_player_id and a "
                "short interpretation of the manager's priorities. Never invent a player or ID."
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
                "State that the options are a preseason baseline. Do not invent statistics, "
                "prices, players, certainty, or transfers. The manager makes the final call."
            ),
            user=json.dumps({"question": question, "engine_facts": facts}),
            json_mode=False,
        )

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
