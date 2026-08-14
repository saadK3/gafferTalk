# Free beta contract

Issue: #32

## User journey

1. Load the versioned synthetic squad locally, or a real finalized squad by
   Team ID after the Gameweek 1 data gate.
2. Confirm the current squad, bank and free transfers.
3. Choose one outgoing player and confirm their selling price.
4. Run one of three deterministic Quick Actions.
5. Compare up to three legal options, evidence and trade-offs.
6. Add one option to the device-local plan and repeat if desired.

## Free Quick Actions

| Action | Historical output | Next-five fixtures | Value |
| --- | ---: | ---: | ---: |
| Best all-rounder | 45% | 35% | 20% |
| Attack the fixtures | 25% | 60% | 15% |
| Stretch the budget | 25% | 20% | 55% |

The action changes backend scoring weights. It is not prompt text and does not
call an LLM.

## Safety and scope

- The deterministic backend remains authoritative for legality and numbers.
- One-player moves preserve position composition and the 15-player squad size.
- Incoming players must be available, affordable, outside the current squad,
  and within the maximum of three players per club.
- Started and finished fixtures are excluded from the upcoming-fixture score.
- A confirmed selling price above the player's current FPL price is rejected as
  impossible instead of increasing the apparent budget.
- A move with no free transfer explicitly shows its four-point hit.
- Wildcard and Free Hit planning are unsupported.
- Plans are stored only in browser local storage and never execute an official
  FPL transfer.
- No FPL password, account, database or Groq key is required.

## Remaining launch gate

The local free version uses live player, price, fixture and availability data
with the synthetic squad. Issue #16 must verify finalized real 2026/27 squads
after the Gameweek 1 deadline before Railway deployment and private beta.
