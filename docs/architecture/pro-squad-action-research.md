# Pro whole-squad action research

Issue #45 extends the named-transfer report into a proactive one-transfer decision. A
confirmed manager can ask what to do this Gameweek without naming a player. The engine
ranks squad concerns, enumerates legal one-player moves, compares the strongest routes
with rolling and returns a versioned report.

## Journey and boundary

```text
confirmed 15-player planning state
  -> /pro/squad-action
  -> choose Safe, Balanced or Aggressive; selling prices may initially be empty
  -> POST /v1/pro/research/squad-action
  -> optimistic whole-squad screen using current price as a maximum sale value
  -> final roll, or request one relevant outgoing player's selling price
  -> deterministic legality check and final transfer/roll decision
  -> Groq selects only backend-approved reason IDs
  -> browser renders the complete structured report
```

The request must contain the confirmed squad, bank and free transfers. Selling prices
are optional and may be supplied incrementally. Public FPL data does not expose each
manager's selling prices, so the first pass uses each player's current market price only
as an optimistic upper bound. An optimistic route is never described as affordable,
legal or final.

If no optimistic route clears the selected threshold, rolling is conclusive and no
price is requested. Otherwise, the response has `needs_selling_price` status and asks
only for the leading route's outgoing player. That exact price is passed through the
canonical legality service. If the route fails, the service either asks for the next
relevant outgoing player's price or returns `insufficient_gain` and recommends rolling.
Confirmed prices are cached for the current browser session and are reused only while
the same 15-player squad remains selected.

## Deterministic scope

Policy version `1.0` evaluates normal one-player transfers only. For every owned player,
it considers every current, available, same-position candidate outside the squad and
passes the route through the canonical transfer-legality service. That service remains
authoritative for position composition, three-per-club, budget, selling prices, free
transfers, paid transfers, points hits and the resulting bank.

The evidence score is the policy introduced in #44, not expected points:

| Component | Weight |
| --- | ---: |
| Points per start | 25% |
| Expected goal involvement per 90 | 25% |
| Minutes reliability | 20% |
| Next-five fixture difficulty | 25% |
| FPL availability | 5% |

Action ordering uses evidence-score improvement, a documented squad-priority bonus,
starting-slot impact, the policy's hit penalty and remaining-bank flexibility. Exact
ties resolve by points hit, remaining bank and stable FPL player IDs. The user's wording
does not change legality or numeric ordering.

## Squad-priority policy 1.0

The report ranks at most five actionable concerns:

- Explicit FPL availability flags are strongest. Severity uses FPL's chance-of-playing
  field, adds starting-slot impact and adds a no-cover penalty when a flagged starter
  would force unavailable positional bench cover.
- Minutes reliability becomes actionable after at least three starts when recorded
  minutes per start are below 72% of a full match.
- Upgrade potential uses the best legal route's evidence gain, with additional weight
  when the outgoing player occupies a starting slot.
- Fixture context is already present in both the outgoing and incoming evidence scores.
- Remaining bank is a deterministic ordering input when otherwise-equivalent actions
  are compared.

An availability concern may remain the top squad problem even when no affordable legal
one-player route can fix it. The report says what needs attention separately from what
can legally be done now.

## Roll and risk policies 1.0

Rolling is the zero-cost baseline. It preserves the bank and increases free transfers
by one up to the current FPL cap. A legal transfer must clear the selected threshold:

| Preference | Normal action threshold | Hit action threshold | Penalty per hit point |
| --- | ---: | ---: | ---: |
| Safe | 12 | 22 | 2.5 score units |
| Balanced | 8 | 16 | 2.0 score units |
| Aggressive | 5 | 11 | 1.5 score units |

These settings express willingness to act on uncertain evidence. They never make an
unavailable, unaffordable or otherwise illegal player eligible. A hit is recommended
only when the leading legal route clears the selected hit threshold after its exact
four-point cost has been policy-adjusted. The report always compares that route with
doing nothing and preserving future flexibility.

## Evidence, confidence and grounding

Bootstrap and fixture data rank the whole squad. Per-Gameweek histories are then loaded
only for the leading concern and leading route players. Confidence is high only when
those material histories are complete, the data is no older than 15 minutes, all
material players have at least five starts and separation from rolling is at least 12.
Medium requires fresh complete evidence, three starts and separation of at least five;
all other cases are low. The reason list exposes the exact inputs.

Groq receives the deterministic action and approved reason IDs. It cannot return player
facts, invent a route or change `transfer` to `roll` (or vice versa). A malformed,
changed or ungrounded selection rejects the entire response; provider failure does not
return a partial report.

## Known limits

- No two-transfer enumeration; that belongs to #46.
- No saved or reconciled multi-Gameweek plan; that belongs to #48.
- Chips are not evaluated.
- The policy does not claim press-conference, predicted-lineup or tactical-role data.
- Selling prices remain manager-confirmed private inputs, but the journey requests them
  progressively only for outgoing players whose routes can change the decision.

## Acceptance coverage

Golden scenarios cover a conclusive price-free roll, a preliminary route becoming an
exact transfer after one confirmation, failure moving to the next relevant outgoing
player, all promising routes resolving to insufficient gain, avoidable and justified
hits, risk preferences, priority ranking, stale/incomplete evidence and invalid prices.
Endpoint and Groq tests cover empty/partial price maps, the versioned contract, grounding
rejection and provider failure. The Pro UI exposes preliminary versus final status, a
focused price request, session reuse, priorities, compared actions, the exact financial
result, hit test, confidence, assumptions and change conditions.
