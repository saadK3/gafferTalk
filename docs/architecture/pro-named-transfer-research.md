# Pro named-transfer research

Status: implemented as the Issue #44 vertical slice
Contract version: `1.0`

## Outcome

The first Pro slice answers a manager who names one player to sell and one to
buy. It does not assume the requested move is correct. The report compares the
validated route with holding, waiting, the strongest other legal same-position
option and any more urgent FPL availability warning elsewhere in the squad.

The browser journey is:

```text
confirmed Team ID planning state
  -> /pro
  -> select outgoing player and confirm exact selling price
  -> search and select a same-position target
  -> POST /v1/pro/research/named-transfer
  -> inspect versioned report, evidence, confidence and change conditions
```

Authentication, persistence, two-transfer routes and saved plans deliberately
remain in later Pro issues.

## Authority boundary

```text
request
  -> canonical bootstrap and fixtures
  -> confirmed squad, bank, free transfers and selling price
  -> deterministic one-transfer legality
  -> deterministic candidate and squad-availability scan
  -> material player element histories
  -> versioned evidence scores, verdict and confidence
  -> model selects 1–3 approved reason IDs
  -> backend renders the conversational summary
```

The deterministic backend owns player identity, evidence, derived metrics,
candidate ordering, legality, bank, hits, verdict and confidence. Groq receives
the verdict and a list of opaque approved reason IDs. It returns only the exact
verdict and selected IDs. Unknown IDs, a changed verdict, malformed JSON or a
provider failure reject the response; none authorize fallback prose.

This makes it impossible for the model-produced selection to introduce a new
player, price, statistic, fixture or route into the displayed answer. The full
report is also rendered directly from backend fields.

## API contract

`POST /v1/pro/research/named-transfer`

Required input:

- Confirmed 15-player squad and squad positions when known
- Confirmed bank and free transfers
- Outgoing player ID
- Exact user-confirmed outgoing selling price
- Target player ID selected from the current catalogue
- Manager's question

The response contains:

- `report.schema_version = "1.0"`
- `buy`, `hold`, `wait` or `avoid` verdict
- Recommended action
- Requested validated route and exact financial state
- Case for and case against
- Best alternative, including holding or waiting
- Squad availability priority
- Opportunity cost and three-Gameweek impact
- Versioned categorical confidence and reasons
- Change conditions
- Structured player evidence with provenance and retrieval time
- Explicit assumptions
- Grounded assistant summary and provider metadata

Invalid or incomplete planning state returns HTTP 422. Invalid upstream FPL
data returns 502, upstream failure returns 503/504, grounding rejection returns
502, and an unavailable model provider returns 503. A failed request never
returns a partial or ungrounded report.

## Evidence policy 1.0

Observed FPL evidence includes:

- Points, starts, minutes, goals, assists and bonus
- Expected goals and expected assists
- Selection percentage
- Recent per-Gameweek points, starts and minutes from element history
- Availability status and FPL player news fields
- Up to five scheduled fixture difficulties

Derived evidence includes:

- Points per start
- Expected goal involvement per 90
- Next-three and next-five average fixture difficulty
- A transparent comparison score

The comparison score is not expected points. It is a bounded ranking input:

| Component | Weight |
| --- | ---: |
| Points per start | 25% |
| Expected goal involvement per 90 | 25% |
| Minutes reliability | 20% |
| Next-five fixture difficulty | 25% |
| FPL availability | 5% |

The requested transfer receives no preference for being named. The target must
be available, same-position, outside the squad and legal under the exact
confirmed financial state.

Verdict thresholds compare target and hold scores and penalize a points hit:

- `buy`: adjusted advantage of at least 8
- `avoid`: adjusted disadvantage of at least 8
- `hold`: adjusted difference within 3
- `wait`: the remaining uncertain middle

These thresholds are versioned policy, not a claim of projected FPL points.

## Confidence policy 1.0

Confidence is deterministic and considers:

- Whether catalogue, fixture and availability data are no older than 15 minutes
- Whether per-Gameweek history loaded for both compared players
- The smaller current-season starts sample
- Separation between the requested and hold scenarios
- Whether the target has an explicit availability percentage or warning

High confidence requires fresh complete evidence, at least five starts, at
least ten comparison-score points of separation and no target availability
qualification. Medium requires fresh complete evidence, at least three starts
and at least five points of separation. Every other case is low confidence.
Every level includes its reasons; low confidence adds another-completed-
Gameweek watch condition.

## Known limits

- Squad priority in this slice identifies stronger explicit FPL availability
  warnings. Full squad opportunity ranking belongs to Issue #45.
- The report describes next-three fixture impact but does not save a plan.
- No external news, predicted lineup, tactical role or press-conference source
  is claimed.
- No precise expected-points forecast is produced.
- Only one normal transfer is evaluated.

## Verification

Golden tests cover a clear buy, ambiguous hold, clear avoid, points hit, urgent
squad availability warning, unavailable target, missing selling price, early
sample, stale evidence, grounded reason selection and provider failure. The
canonical transfer-legality suite remains authoritative.
