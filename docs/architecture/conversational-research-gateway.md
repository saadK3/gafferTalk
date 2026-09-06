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
- The existing research engines remain responsible for FPL data, legality and calculations.
- The final explanation is built only from the approved report and its grounded reasons.

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
