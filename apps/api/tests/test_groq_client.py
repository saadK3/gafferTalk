import json

import httpx
import pytest

from gaffertalk_api.domain.models import Club, Money, Player, Position
from gaffertalk_api.integrations.llm.groq import GroqConversationClient


@pytest.mark.anyio
async def test_groq_interpretation_must_preserve_selected_player() -> None:
    selected = Player(
        id=12,
        web_name="Yates",
        club=Club(id=1, name="Example", short_name="EXA"),
        position=Position.MIDFIELDER,
        current_price=Money(tenths=45),
        status="a",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "outgoing_player_id": 12,
                                    "interpretation": "Prioritise easier fixtures.",
                                }
                            )
                        }
                    }
                ]
            },
        )

    http_client = httpx.AsyncClient(
        base_url="https://groq.test/openai/v1/", transport=httpx.MockTransport(handler)
    )
    client = GroqConversationClient(
        api_key="test-key",
        model="test-model",
        base_url="https://groq.test/openai/v1/",
        timeout_seconds=1,
        client=http_client,
    )
    try:
        intent = await client.interpret("Who replaces Yates?", (selected,), 12)
    finally:
        await http_client.aclose()

    assert intent.outgoing_player_id == 12
    assert intent.interpretation == "Prioritise easier fixtures."
