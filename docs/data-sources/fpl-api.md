# FPL API data availability

Status: observed against the live 2026/27 service on 2026-08-12 (Asia/Karachi),
before the Gameweek 1 deadline.

## Decision summary

The JSON endpoints hosted at `fantasy.premierleague.com/api/` provide enough
global data to build a player, team, fixture, and rules catalogue. A public Team
ID provides manager metadata and historical, deadline-finalized state.

A Team ID does **not** provide the manager's live squad before a deadline. The
live squad endpoint requires FPL authentication, which GafferTalk will not ask
users to provide. Public state also does not expose the exact number of free
transfers or current player selling values needed to guarantee transfer
legality.

Therefore, GafferTalk must support two distinct modes:

1. **Snapshot mode:** after a deadline, load the last public squad and clearly
   label its Gameweek and freshness. Recommendations using unchanged state may
   be evaluated against this snapshot.
2. **Current-planning mode:** ask the user to confirm any transfers made since
   the snapshot, current bank, free transfers, and selling prices of outgoing
   players. A recommendation must not be described as guaranteed legal until
   this state is known.

The pre-season onboarding promise `Team ID -> current squad` is not achievable
from public Team ID endpoints alone. Before Gameweek 1, users must enter/import
their squad or wait until the first deadline-finalized picks become public.

### Why some third-party sites appear to show a pre-season squad

LiveFPL was inspected on 2026-08-12 as a comparison. Its public manager endpoint
still identified the prior season's final Gameweek. Its planner snapshot endpoint
returned 15 players for a valid manager ID, but the same response explicitly
reported `preseason: true` and `source: "autopick"`. The displayed players were
therefore a generated planning fallback, not the manager's unpublished 2026/27
FPL selection.

Other products may similarly display a previous deadline snapshot, ask the user
to build/import a squad, generate an assumed squad, or use an authenticated
browser/session mechanism. The presence of 15 players in a UI is not evidence
that Team ID exposes the live private squad. GafferTalk must label generated and
snapshot squads honestly and must not present either as observed current state.

## Source status and support level

These are first-party endpoints in the sense that they are served from the
official Fantasy Premier League domain and used by the FPL web application.
They are not treated as a stable, versioned public API contract: no OpenAPI or
schema endpoint was found, no service-level agreement was observed, and fields
may change without notice.

GafferTalk should isolate upstream payloads behind adapters, validate every
response, retain sanitized contract fixtures, and fail closed when fields
required for legality are absent.

Commercial-use and data-retention terms require a separate product/legal review
before public hosting. This research establishes technical availability only.

## Observed endpoint matrix

| Endpoint | Pre-GW1 result | Public | Useful data | Product treatment |
| --- | ---: | --- | --- | --- |
| `/bootstrap-static/` | 200 | Yes | Gameweeks, players, clubs, positions, chips, scoring and squad rules | Shared catalogue; cache and validate |
| `/fixtures/` | 200 | Yes | All fixtures, event assignment, kickoff, difficulty, scores/status | Shared catalogue; refresh periodically |
| `/element-summary/{player_id}/` | 200 | Yes | Player fixtures, current-season history and prior-season history | Cache per player; tolerate missing history |
| `/event-status/` | 200 | Yes | Bonus-processing/event status | Operational supplement only |
| `/entry/{team_id}/` | 200 for valid ID | Yes | Public manager metadata, rank/points and last-deadline bank/value | Minimize PII; snapshot metadata only |
| `/entry/{team_id}/history/` | 200 | Yes | Past seasons, finalized Gameweek history and chip usage | Historical snapshot; no live free-transfer count |
| `/entry/{team_id}/transfers/` | 200, empty pre-GW1 | Yes | Public transfers when released | Do not assume pre-deadline visibility |
| `/entry/{team_id}/event/{gw}/picks/` | 404 before GW1 deadline | Yes after applicable deadline, to be revalidated | Deadline-finalized picks and entry history | Never call it the live squad |
| `/my-team/{team_id}/` | 403 without credentials | No | Live squad and private transfer state | Explicitly unsupported; never request FPL credentials |
| `/me/` | 200 with `player: null` anonymously | Partially | Logged-in profile only when authenticated | Not needed |

Invalid public IDs return JSON `404` responses such as
`{"detail":"No Entry matches the given query."}`. Missing pre-deadline picks
returned `{"detail":"Not found."}`. Consumers must branch on HTTP status and
must not infer that every 404 means an invalid Team ID.

## Global data observed

The 2026/27 pre-season snapshot contained:

- 38 Gameweeks
- 20 clubs
- 577 players
- 380 fixtures
- Gameweek 1 deadline: `2026-08-21T17:30:00Z`
- Squad size: 15
- Maximum players per club: 3
- Initial budget: 1000 integer units (£100.0m at multiplier 10)
- Maximum banked extra free transfers: 4, implying up to 5 available
- Selling-price fee setting: 0.5

Money must be stored as integer tenths of a million. Float arithmetic is not
acceptable for legality checks.

Player records include current price, ownership, status, news, chance-of-playing
fields, minutes, FPL production and several underlying metrics. These fields do
not provide reliable expected minutes, starting probability, rotation risk,
tactical role, or an independent future expected-points projection.

Pre-season team-strength fields were null or zero in the observed payload, so
they cannot be assumed ready for an opening-week projection model.

## User-state classification

| Required state | Classification | Notes |
| --- | --- | --- |
| Team ID and public manager metadata | Observed | Team ID identifies a public entry; it is not authentication |
| Last finalized squad | Observed after its deadline | Picks were unavailable before GW1; revalidate after the first deadline |
| Current live squad | Unavailable publicly | Authenticated `/my-team/` is deliberately unsupported |
| Last-deadline bank and squad value | Observed snapshot | Public entry fields are null pre-season and stale after new transfers |
| Current bank | User-supplied or derived with caveats | Cannot be guaranteed from Team ID during an open transfer window |
| Free transfers available now | User-supplied | Historical activity may help derive an estimate but is not authoritative live state |
| Current player market price | Observed globally | `now_cost`, integer tenths |
| Exact selling price | User-supplied | Depends on purchase price and gains; not present in the public pre-deadline state |
| Transfer hits already taken | User-supplied until deadline-finalized | Finalized history exposes event transfer cost after the fact |
| Injury/status/news | Observed but incomplete | FPL fields are useful signals, not a starting guarantee |
| Expected minutes or xPts | Derived | Must be produced and versioned by GafferTalk or another licensed source |

## Deadline behavior and required revalidation

Observed before Gameweek 1:

- `current_event` was null and Gameweek 1 was `is_next`.
- A valid entry existed, but `last_deadline_bank` and `last_deadline_value` were
  null.
- `/entry/{valid_team_id}/event/1/picks/` returned 404.
- `/entry/{valid_team_id}/transfers/` returned an empty array.
- `/my-team/{valid_team_id}/` returned 403 without authentication.

The following assumptions are intentionally **not** marked verified yet:

- The exact public picks schema for 2026/27
- When picks and transfers become public relative to each deadline
- Whether public transfers reveal moves during an active transfer window
- Whether last-deadline bank/value update atomically with picks
- Blank, double, or rescheduled Gameweek behavior

Create a follow-up revalidation task immediately after the Gameweek 1 deadline.
Until then, adapters must treat the picks schema and release timing as provisional.

## Caching, browser access, and throttling

Observed headers:

- `/bootstrap-static/`: `cache-control: max-age=300,
  stale-while-revalidate=3600, stale-if-error=3600`
- Other tested public endpoints: `max-age=0, no-cache, no-store,
  must-revalidate`
- No `X-RateLimit-*` or `Retry-After` headers were observed.
- Ten sequential requests to the small `/event-status/` endpoint returned 200;
  this is not evidence of an unlimited or stable rate limit.
- Responses did not include an `Access-Control-Allow-Origin` header for a local
  browser origin and declared `cross-origin-resource-policy: same-origin`.

All FPL requests should therefore go through the GafferTalk backend. Apply
bounded timeouts, limited retries with jitter for transient failures, request
coalescing, and application caching. Start conservatively:

- Bootstrap: cache for five minutes and permit a stale fallback.
- Fixtures/global catalogue: cache for five minutes pre-deadline; shorten only
  during live matches if the product needs live state.
- Entry and picks: cache briefly per Team ID and never log manager names.
- Player summaries: cache for at least one hour outside live recalculation jobs.
- On 429 or 5xx: honor `Retry-After` when present and back off.

Do not download global data once per user request.

## Required onboarding and recommendation UX

When only a Team ID is available, display the snapshot Gameweek and timestamp.
Before calculating transfers, collect or confirm:

1. Any transfers made since the displayed snapshot
2. Current money in the bank
3. Free transfers available
4. Selling price for each proposed outgoing player when exact legality depends
   on it

Each field must carry one provenance value:

```text
observed | derived | user_supplied | unavailable
```

If required state is unavailable, the backend should return a structured
`missing_user_state` result. The LLM may ask for that state; it may not invent it
or downgrade an approximate route into a guaranteed legal recommendation.

## Fixture policy

Sanitized contract samples live in `tests/fixtures/fpl/`. They preserve the
observed response shapes and units while replacing manager identity, IDs, club
names and player names. They are not projection-training data and must not be
silently refreshed from production.

Every fixture update should record the observation date in the fixture README,
remove personal data, and be reviewed as an upstream contract change.
