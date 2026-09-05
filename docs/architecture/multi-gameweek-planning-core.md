# Multi-Gameweek planning core

Status: implemented as vertical slice 1 in Issue #63
Contract version: `1.0`

## Outcome

The planning core finds legal, financially feasible ways to add one named target
over the next one or two FPL Gameweeks. It is a deterministic tool for the future
research agent. It does not decide which route is best football advice.

```text
confirmed squad and private financial state
  + current FPL catalogue and rules
  + target, horizon, protected players, bank and hit constraints
  -> bounded transfer blueprints
  -> possible one- or two-Gameweek schedules
  -> canonical legality validation at every deadline
  -> primary feasibility route and up to two alternatives
```

The primary route is ordered by fewest hit points, earliest target arrival, fewest
transfers and highest remaining bank. Stable player IDs break remaining ties. This
is a transparent feasibility ordering, not a performance score or recommendation.
Slice 3 will combine these routes with sourced evidence and manager priorities to
form an opinion.

## Contracts

`MultiGameweekRouteRequest` contains:

- A finalized squad snapshot used as the baseline
- Manager-confirmed bank and free transfers
- Any currently known selling prices
- One target player
- One or two consecutive upcoming Gameweeks
- Protected squad players
- Maximum total hit and minimum final bank

`MultiGameweekRouteReport` distinguishes:

- `routes`: the relevant starting selling prices are confirmed
- `needs_selling_prices`: a provisional leading route names only the prices it needs
- `target_already_owned`: no acquisition route is necessary
- `no_legal_route`: the protected-player constraints make target replacement impossible
- `no_route_found_within_bounds`: the bounded search found none; this is not a proof
  that no route exists outside its candidate or transfer limits

Routes contain Gameweek-by-Gameweek actions, exact state arithmetic at the stated
prices, the selling-price basis for every outgoing player, resulting squads, bank,
free transfers available for the following Gameweek, and accumulated hit cost.

## State-transition policy

A roll uses no transfer and adds one free transfer for the following Gameweek, up
to the maximum exposed by the current FPL rules.

A transfer batch is passed to `TransferLegalityService`, which remains authoritative
for player references, squad shape, club limits, money and the hit at that deadline.
The next Gameweek receives one new free transfer in addition to any unused free
transfers, capped by the current rules. Each resulting squad becomes the input to
the following deadline.

The current catalogue price is used for a future purchase. Therefore every route is
conditional on prices remaining unchanged until execution and must be recalculated
before acting. When an outgoing player's private selling price is missing, current
price is only an optimistic upper bound and the report remains provisional.

## Search boundary

Version 1 considers:

- At most two consecutive Gameweeks
- At most three total transfers
- Direct target replacement plus at most two funding transfers
- At most four cheapest same-position replacements per possible funding sale
- At most 25,000 scheduled-route simulations

Funding candidates are selected by price, not form, fixtures, expected points or
another football metric. Player availability does not determine transfer legality;
the later evidence and decision layers must assess whether a legal route is sensible.

The search schedules a complete route immediately, after a roll, or by making funding
moves before the final target-purchase batch. It does not consider chips, selling a
newly purchased intermediary, arbitrary transfers after the target arrives, or plans
beyond the declared bounds.

## Relationship to the research assistant

This slice establishes **what can be done**. It deliberately does not establish
**what should be done**.

The future research coordinator will call this service, identify the players and
trade-offs that distinguish its routes, gather attributable evidence, and then
explain one recommendation and up to two credible alternatives. Keeping feasibility
separate prevents a language model from inventing budgets, hits or legal routes.

## Verification

Tests cover direct affordability, rolling, a three-transfer route, hit constraints,
target ownership, protected players, missing selling prices, invalid Gameweek/squad
context, deterministic ordering and disclosed bounds. The canonical one-Gameweek
legality and existing route-research suites run alongside the new tests.
