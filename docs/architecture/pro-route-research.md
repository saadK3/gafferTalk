# Pro bounded route research

Issue #46 adds a route-to-target vertical at `/pro/routes`. A manager selects a
canonical target, may protect or require the sale of owned players, chooses a one- or
two-transfer boundary and may reserve part of the bank. The backend—not the language
model—enumerates, validates and ranks every supported route.

## Journey and contract

```text
confirmed 15-player planning state
  -> select target and explicit keep/sell/bank constraints
  -> POST /v1/pro/research/route with an empty or partial selling-price map
  -> bounded optimistic route enumeration
  -> no-supported-route, or request prices for only the leading route's outgoing players
  -> canonical exact legality validation
  -> recommended or strategically discouraged exact route
  -> Groq selects only approved reason IDs
```

The versioned report distinguishes three statuses:

- `needs_selling_prices`: a provisional screen passed using current prices only as
  maximum possible selling values. It is not described as affordable or legal.
- `route`: the selected route passed canonical legality with every relevant outgoing
  selling price confirmed.
- `no_legal_route`: no route inside the declared boundary satisfies the target and
  constraints, even under optimistic selling values, or all examined exact routes fail.

`recommended` and `discouraged` are strategic verdicts, separate from legality. A
manager override exposes the strongest supported exact route while preserving a
`discouraged` verdict.

## Search boundary

The target must be outside the squad and currently available. A one-transfer route
replaces an owned player in the target's position. A two-transfer route adds the target
and one secondary same-position replacement, then validates the final 15-player squad.
This structure still permits the second transfer to free funds or a club slot.

To keep search latency bounded against the full catalogue, each secondary position pool
is the stable union of the top 30 evidence-ranked players and 10 cheapest available
players. The resulting maximum is 40 candidates per position. Stable player IDs resolve
ties. The report exposes routes examined, candidate limit and measured search time.

Routes are ranked by the quality of the resulting squad:

1. Sum the incoming evidence scores and subtract the outgoing scores.
2. Apply the selected policy's exact hit penalty.
3. Prefer fewer hit points, more remaining bank and stable player IDs when adjusted
   gains tie.

The shared evidence score uses observed output, expected goal involvement, minutes,
fixtures and availability. It is not projected FPL points.

## Constraints and legality

- Preserved players cannot be transferred out.
- An excluded owned player must be transferred out; no more than two can be required.
- Excluded non-owned players cannot enter the final squad.
- Minimum remaining bank is enforced by the canonical legality result.
- The final squad must preserve position composition, contain 15 unique players and
  remain within the three-player club limit.
- Free-transfer use, paid transfers, four-point hits and resulting bank come only from
  `TransferLegalityService`.

Public FPL data does not expose manager selling or purchase prices. Current prices are
used only for optimistic screening. Exact selling prices are manager-confirmed and
already incorporate purchase-price effects. The API accepts optional purchase prices to
cross-check FPL's profit-sharing calculation, but the browser does not require them.
Confirmed selling prices are cached only for the same squad in the current browser
session.

## Grounding and failures

Groq receives only deterministic status, verdict and approved reason IDs. It cannot add
players, prices, statistics, fixtures or routes, and a changed or unknown selection
rejects the entire response. Upstream and provider failures return no partial report.
Unknown targets, contradictory constraints and impossible prices return actionable
validation errors.

## Acceptance coverage

Golden tests cover one- and two-transfer routes, exact price progression, budgets,
preserve/exclude constraints, hit effects, no-route versus discouraged outcomes,
manager override, purchase/selling-price consistency, deterministic ordering and the
latency/candidate cap. The shared canonical legality suite covers positions, squad size,
club limits, ownership and duplicate players. Endpoint and grounding tests cover the
versioned boundary and provider failure. Browser acceptance uses a real finalized squad
to exercise target search, a preserved-player no-route result, exact two-price
confirmation and session reuse.

## Known limits

- No three-transfer current-Gameweek search.
- No chip-assisted routes.
- No arbitrary future chain or three-Gameweek persistence; that belongs to #48.
- Candidate ranking uses documented evidence scores, not expected points.
