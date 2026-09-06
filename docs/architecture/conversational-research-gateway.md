# Conversational research gateway

The conversational gateway is the front door for the personal research assistant. It keeps
natural language flexible while keeping research decisions bounded and inspectable.

```text
manager turn
    |
    v
Groq interpreter (intent and constraints only)
    |
    +--> clarification or scope response
    |
    v
validated GeneralResearchRequest
    |
    v
deterministic research capability
    |
    v
evidence-backed report -> constrained explanation
```

## Responsibilities

- The interpreter maps wording such as "roll", "bank" and "hold" to a supported capability.
- The interpreter may extract names, horizons, hit limits, protected players and objectives, but
  it does not choose a player or call FPL tools.
- The gateway validates the interpreter result, resolves protected names against the confirmed
  squad and asks for missing manager state before research runs.
- When a route needs an exact outgoing selling price, the response includes a
  `selling_price_requests` array. Each item contains the player ID, display name, current FPL
  price as an upper-bound reference, and a reason. Clients can render a price input directly and
  must not parse the assistant message to discover this request.
- The existing research engines remain responsible for FPL data, legality and calculations.
- The final explanation is built only from the approved report and its grounded reasons.

Example response fragment when a price is needed:

```json
{
  "selling_price_requests": [
    {
      "player_id": 8,
      "player_name": "Player 8",
      "current_fpl_price_tenths": 90,
      "reference_price_basis": "current_price_upper_bound",
      "reason": "Confirm this player's actual selling price to validate the proposed route."
    }
  ]
}
```

`current_fpl_price_tenths` is not the manager's selling price. It is the maximum public price the
planner can use as an optimistic reference until the manager confirms the actual value in the
next turn. The client can submit that value using the same `conversation_id` and a
`selling_prices_tenths` map; it does not need to resend the squad because the gateway retains the
confirmed state for the conversation.

The local implementation keeps a bounded in-memory context for short conversations. It stores the
confirmed squad, manager constraints and the last eight turns. Persistent context belongs to the
personal application slice.

## Local acceptance suite

Run the five representative questions with a public team ID:

```bash
python -m gaffertalk_api.cli research-suite 3906635 --assume-current-prices
```

The `--assume-current-prices` flag is deliberately explicit. It is suitable for testing only;
production routes should use manager-confirmed selling prices. The suite also accepts
`--free-transfers` when the public team snapshot does not provide the manager's current number.
