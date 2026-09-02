# Pro conditional three-Gameweek plans

Issue: #48

## Outcome

An authenticated manager can turn an account-owned, validated named-transfer
report into an active conditional plan. The plan prescribes only the current
Gameweek and the following two while retaining five Gameweeks of fixture evidence.
It is a durable decision artifact, not an automatic transfer schedule.

## Authority boundary

`ProPlanService` builds and reconciles plans deterministically. The language model
does not create plan actions, prices, Gameweeks, conditions, confidence or stale
state. A plan can only be built from a persisted report tied to the workspace's
current confirmed squad-state version.

The plan contract enforces:

- exactly three ordered horizon Gameweeks;
- no more than two transfers in the current Gameweek;
- no more than three transfer actions across the full horizon;
- `plan`, `watch` or `alternative` wording for future actions;
- persisted financial state, evidence, conditions, assumptions and confidence.

## Data and persistence

`ProPlanLoader` retrieves the newest finalized public squad, current player
availability and the fixture schedule. It records the public snapshot Gameweek,
the 15 public player IDs, player statuses, five evidence Gameweeks and a stable
SHA-256 signature of the relevant fixture schedule.

`workspace_plans` stores immutable plan data plus mutable lifecycle metadata. A
new saved plan supersedes the prior active or stale plan but does not delete it.
Plans are account-scoped through their workspace and retain references to the
source report and squad-state version.

Supported lifecycle values are `active`, `stale`, `completed`, `superseded` and
`abandoned`. Only the current active or stale plan can be reconciled, completed or
abandoned.

## Staleness and reconciliation

Reconciliation compares a saved plan with fresh public evidence and the manager's
current private values. The deterministic stale reasons are:

- newer finalized public snapshot;
- public-squad player change;
- confirmed squad-state version change;
- bank, free-transfer or relevant selling-price change;
- involved player unavailability;
- relevant fixture-schedule change;
- current deadline passed.

Squad, snapshot and financial changes are material because public FPL data cannot
reconstruct all live private state. A material result marks both the plan and the
current squad state stale. New workspace research is blocked until the manager
confirms a new complete planning state. Fresh research and saving then create new
report and plan versions while preserving history.

Player, fixture and deadline changes stale the plan and require recalculation, but
do not by themselves claim that the manager's private squad state changed.

## API and browser boundary

The authenticated workspace exposes:

```text
POST  /v1/pro/workspace/plans/preview
POST  /v1/pro/workspace/plans
POST  /v1/pro/workspace/plans/{plan_id}/reconcile
PATCH /v1/pro/workspace/plans/{plan_id}
```

The Next.js same-origin backend-for-frontend allowlists only these explicit route
shapes and forwards the Supabase access token server-side. UUID path validation
prevents arbitrary upstream path forwarding.

The workspace shows active/stale state, the three-Gameweek timeline, conditions,
alternatives, assumptions, plan history, reconciliation inputs and lifecycle
controls. Responsive layouts collapse the plan timeline and reconciliation form
for tablet and mobile widths.

## Failure behavior

- Missing or stale squad state returns a structured conflict rather than a plan.
- A report from another account or an older squad version is rejected.
- FPL timeout, unavailable, invalid-response and not-found failures reuse the
  canonical upstream error mapping.
- A save race after preview returns `workspace_state_stale`; it never persists a
  plan against a replaced current squad.
- Historical and cross-account plans cannot be reconciled or relabeled.

## Verification

The deterministic suite covers horizon and transfer bounds, every stale reason,
material research blocking, version preservation, lifecycle restrictions and
cross-account access. The web client suite verifies explicit same-origin plan
routes. Private-beta qualification in issue #51 owns full hosted desktop/mobile
journeys against real authenticated sessions.

## Known limits

- Plans are currently derived from persisted named-transfer reports. The unified
  five-intent Pro workspace is completed through issues #49–#51.
- No chip optimization, notifications, automatic execution or horizon longer than
  three Gameweeks is supported.
- Future prices and free transfers are conditional estimates and must be
  recalculated before acting.
