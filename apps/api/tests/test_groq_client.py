import json

import httpx
import pytest

from gaffertalk_api.domain.models import Club, Money, Player, Position
from gaffertalk_api.domain.pro_research import (
    GroundedReason,
    ProDecisionReport,
    ProVerdict,
    SquadActionCandidate,
    SquadActionKind,
    SquadActionReport,
    SquadActionStatus,
)
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
                                    "strategy": "fixture_first",
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
    assert intent.strategy == "fixture_first"
    assert intent.interpretation == "Prioritise easier fixtures."


def pro_report() -> ProDecisionReport:
    return ProDecisionReport.model_construct(
        verdict=ProVerdict.HOLD,
        recommended_action="Hold Bruno; the requested move does not offer a clear enough gain.",
        grounded_reasons=(
            GroundedReason(
                id="strongest_case_against",
                text="Holding Bruno preserves one transfer.",
            ),
            GroundedReason(
                id="planning_impact",
                text="The next-three fixture comparison favors holding.",
            ),
        ),
    )


@pytest.mark.anyio
async def test_pro_synthesis_can_only_select_validated_reason_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        supplied = json.loads(body["messages"][1]["content"])
        assert supplied["available_reason_ids"] == [
            "strongest_case_against",
            "planning_impact",
        ]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "verdict": "hold",
                                    "reason_ids": ["strongest_case_against"],
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
        answer = await client.synthesize_pro_report("Bruno to Odegaard?", pro_report())
    finally:
        await http_client.aclose()

    assert "Holding Bruno preserves one transfer." in answer
    assert "If you still prefer the requested move" in answer


@pytest.mark.anyio
async def test_pro_synthesis_rejects_unknown_reason() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"verdict": "hold", "reason_ids": ["invented_fact"]}
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
        with pytest.raises(ValueError, match="absent"):
            await client.synthesize_pro_report("Bruno to Odegaard?", pro_report())
    finally:
        await http_client.aclose()


def squad_action_report() -> SquadActionReport:
    return SquadActionReport.model_construct(
        status=SquadActionStatus.ROLL,
        recommended_action=SquadActionCandidate(
            action=SquadActionKind.ROLL,
            evidence_gain=0,
            policy_adjusted_gain=0,
            remaining_bank=Money(tenths=10),
            free_transfers_used=0,
            free_transfers_after=2,
            points_hit=0,
            budget_status="not_applicable",
            explanation="Roll the transfer and preserve flexibility.",
        ),
        grounded_reasons=(
            GroundedReason(
                id="recommended_action", text="Roll the transfer and preserve flexibility."
            ),
            GroundedReason(id="leading_priority", text="No urgent squad issue is present."),
            GroundedReason(
                id="roll_comparison",
                text="No legal transfer clears the documented threshold.",
            ),
        ),
    )


@pytest.mark.anyio
async def test_squad_action_synthesis_preserves_action_and_reason_boundary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        supplied = json.loads(json.loads(request.content)["messages"][1]["content"])
        assert supplied["status"] == "roll"
        assert supplied["available_reason_ids"] == [
            "recommended_action",
            "leading_priority",
            "roll_comparison",
        ]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"status": "roll", "reason_ids": ["roll_comparison"]}
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
        answer = await client.synthesize_squad_action_report(
            "Should I roll?", squad_action_report()
        )
    finally:
        await http_client.aclose()

    assert answer == (
        "Roll the transfer and preserve flexibility. "
        "No legal transfer clears the documented threshold."
    )


@pytest.mark.anyio
async def test_squad_action_synthesis_rejects_changed_action() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"status": "transfer", "reason_ids": ["roll_comparison"]}
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
        with pytest.raises(ValueError, match="changed"):
            await client.synthesize_squad_action_report("Should I roll?", squad_action_report())
    finally:
        await http_client.aclose()
