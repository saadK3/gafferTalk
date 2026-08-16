# Free beta contract

Issues: #32, #35

## User journey

1. Load the versioned synthetic squad locally, or a real finalized squad by
   Team ID after the Gameweek 1 data gate.
2. Confirm the current squad, bank and free transfers.
3. Either choose one outgoing player, or ask GafferTalk to find who to sell for
   a named incoming target.
4. Confirm the outgoing player's actual FPL selling price.
5. Ask a transfer question in natural language, optionally starting from one of
   three suggested prompts.
6. Compare the grounded answer and up to three legal options, evidence and
   trade-offs.
7. Add one option to the device-local plan and repeat if desired.

## Free allowance

- Each anonymous browser receives three successful transfer questions per FPL
  Gameweek.
- A random browser ID is stored locally and sent to the API. The API, not browser
  state, enforces the allowance in SQLite.
- Usage is keyed by browser ID and the official current/next FPL Gameweek, so a
  new Gameweek starts a fresh allowance.
- Invalid requests and Groq/provider failures do not consume a question.
- Explicit named targets are checked for ownership, matching position,
  availability, budget and club limits before quota is reserved or Groq is
  called. Misspellings are matched conservatively against current FPL players.
- “Find who to sell” evaluates same-position one-transfer routes without Groq or
  quota use, suggests the lowest-sacrifice plausible outgoing player, and then
  requires the user's private selling price before completing the recommendation.
- Clearing browser storage creates a new anonymous identity. Accounts are
  required before this becomes an abuse-resistant public entitlement system.

## Question strategies

Groq maps the question to one of three supported strategies. The deterministic
engine then applies the documented weights:

| Action | Historical output | Next-five fixtures | Value |
| --- | ---: | ---: | ---: |
| Best all-rounder | 45% | 35% | 20% |
| Attack the fixtures | 25% | 60% | 15% |
| Stretch the budget | 25% | 20% | 55% |

Groq interprets priorities and explains the completed result. It never decides
transfer legality, prices, score calculations or the ranked order.

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
- No FPL password or FPL login is required.
- A server-only Groq key is required for the Free conversational flow.
- Local usage is persisted in `.data/gaffertalk.sqlite3`, which is gitignored.

## Remaining launch gate

The local Free version uses live player, price, fixture and availability data
with the synthetic squad. Issue #16 must verify finalized real 2026/27 squads
after the Gameweek 1 deadline before Railway deployment and private beta. A
Railway deployment must mount a persistent volume for the SQLite file or move
usage records to PostgreSQL before inviting testers.
