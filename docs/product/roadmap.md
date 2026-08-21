# GafferTalk MVP roadmap

Last updated: 2026-08-16

## Launch strategy

GafferTalk will launch after the 2026/27 Gameweek 1 deadline and before the
Gameweek 2 deadline.

Public FPL endpoints do not expose a manager's unpublished pre-deadline squad.
After a deadline, Team ID can load the finalized public squad without FPL
authentication. This makes the first deadline a required data-validation gate,
not merely a marketing date.

The current observed schedule is:

| Event | UTC | Pakistan time |
| --- | --- | --- |
| Gameweek 1 deadline | 2026-08-21 17:30 | 2026-08-21 22:30 PKT |
| Final Gameweek 1 fixture | 2026-08-24 19:00 | 2026-08-25 00:00 PKT |
| Target public launch | 2026-08-25–26 | 2026-08-25–26 PKT |
| Gameweek 2 deadline | 2026-08-28 17:30 | 2026-08-28 22:30 PKT |

FPL may change fixtures or deadlines. Recheck the live bootstrap and fixture
feeds before scheduling beta invitations or launch communications.

## MVP promise

```text
Team ID
  -> latest finalized squad
  -> confirm changes since the deadline
  -> ask a transfer question
  -> receive legal, data-driven options with evidence
```

GafferTalk will not request an FPL password or present a generated, previous, or
deadline-finalized squad as live private state.

## Milestones

### M0 — Data feasibility — complete

Completed through issue #1 and PR #17.

Outcome:

- Verified global and manager endpoint availability
- Identified public snapshot and private live-state boundaries
- Defined missing-state provenance and fallback behavior
- Added sanitized contract fixtures and validation tests

### M1 — Core vertical slice — target August 22

Build before the GW1 deadline where possible, then validate the successful
2026/27 picks contract immediately after the deadline.

Required outcomes:

- Canonical FPL domain models
- Validated global player, team, fixture and rules client
- Manager and finalized-squad loading by Team ID
- Snapshot freshness and provenance in the UI
- Current bank/free-transfer/recent-change confirmation
- Deterministic transfer-legality rules
- Canonical legality scenarios
- One-player legal replacement search
- Successful post-GW1 picks-schema revalidation

Exit criterion:

> A real Team ID loads the correct finalized GW1 squad, the manager can confirm
> current state, and the backend returns only legal replacement candidates.

### M2 — Recommendation quality — target August 24

Required outcomes:

- Initial versioned player ranking/projection model
- Structured AI tool contracts
- Chat connected to deterministic replacement search
- Recommendation evidence, assumptions and freshness
- Captain ranking if it does not threaten the replacement flow
- Failure telemetry for bad data, tool failures and rejected recommendations

Exit criterion:

> The product explains useful recommendations without inventing players,
> budgets, projections, or legality.

### M3 — Private beta — target August 25

Test with 10–20 managers using real post-deadline squads.

Observe:

- Team-loading success rate
- Incorrect or stale squad reports
- Missing-state questions users struggle to answer
- Illegal transfer or budget failures
- Whether users ask a second question
- Whether explanations create appropriate trust

Only P0 defects should interrupt the beta. New feature ideas move to Post-MVP.

### M4 — Public launch — target August 25–26

Launch only if the complete core loop is reliable and the hosted service has:

- Error monitoring and request logging without manager PII
- Anonymous usage limits
- Basic privacy and source-available licensing pages
- Responsive onboarding and recommendation UI
- A rollback path
- Confirmed hosted operating costs

The public launch must occur early enough to observe and fix failures before the
Gameweek 2 deadline on August 28.

## Critical implementation order

```text
#3 domain models
  -> #4 global data client
  -> #5 manager/squad loading
  -> #6 squad UI and #15 current-state confirmation
  -> #7 legality rules + #12 scenario suite
  -> #8 replacement search
  -> #9 tool contracts
  -> #10 chat integration
  -> #11 evidence and assumptions
```

Issue #16 is a calendar dependency: it begins immediately after the GW1
deadline and can change the squad adapter if the observed live response differs
from the sanitized provisional contract.

## Current development status

Implemented before the GW1 deadline:

- Team ID lookup and current-team confirmation flow
- Deterministic transfer legality
- Live-FPL one-player ranking baseline
- `POST /v1/recommendations/transfers` contract
- Branded recommendation screen at `/recommend`
- Groq-backed interpretation and grounded explanation boundary
- Free conversational beta with balanced, fixture-first and value-first legal
  one-player recommendations
- Backend-enforced allowance of three successful questions per browser and
  official FPL Gameweek, with failed requests refunded
- Device-local transfer planning that updates the synthetic/confirmed squad,
  bank and free-transfer count without an account or database

## Post-GW1 launch gate

An initial post-deadline observation on August 22 confirmed the successful
2026/27 picks schema, 15-player squad shape, captaincy fields, absence of public
selling prices, and synchronization of finalized bank/value fields. Sanitized
contract fixtures now cover that response.

Public launch remains blocked until issue #16 completes transfer-release timing
validation and the broader real-squad journey below. The launch gate is
satisfied only when:

1. At least three real Team IDs load the correct 15-player GW1 squad.
2. Captain, vice-captain, bench order, bank and squad value match FPL.
3. A manager can record post-deadline changes and confirm current state.
4. The recommendation API returns legal options for those real squads.
5. Groq explanations contain no player, price, fixture or legality claim that
   is absent from the deterministic engine result.
6. The complete Team ID → confirmation → question → recommendation journey
   passes on desktop and mobile before private-beta invitations are sent.

## Scope guardrails

The following are not launch requirements:

- FPL credential authentication
- Automatic transfers
- Wildcard or Free Hit optimization
- Multi-Gameweek autonomous planning
- Mini-league or rival analysis
- Native applications
- Push notifications
- Advanced dashboards
- A sophisticated machine-learning projection model

Authentication, payments, PostgreSQL and Redis should be added only when the
hosted MVP genuinely needs them. They must not delay validation of the core
recommendation loop.

## Owner actions

Before private beta, the product owner should:

- Recruit 10–20 willing FPL managers
- Prepare a support/privacy contact email
- Decide the initial hosted domain
- Approve a small LLM and infrastructure test budget
- Review launch copy so finalized snapshots are not described as live squads

No tester should share an FPL password or session cookie.
