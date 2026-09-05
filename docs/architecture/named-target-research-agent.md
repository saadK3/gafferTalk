# Named-target research agent

Slice 3 connects the deterministic planning and evidence tools into the first
complete research-agent loop. It accepts a named-player question, gathers only
the information needed for that question, and returns one selected route with up
to two alternatives.

## Request flow

```text
Natural-language question + confirmed squad state
  -> cheap scope check (no FPL calls for unrelated questions)
  -> resolve target and constraints from the question
  -> deterministic route planner
  -> evidence loader for the target and route players
  -> deterministic comparison and approved reasons
  -> optional Groq wording constrained to those reasons
  -> inspectable report + assistant message
```

The endpoint is `POST /v1/agent/research/named-target`.

The request includes the current squad, bank, free transfers and any known
selling prices. The question can state a target, a one- or two-Gameweek horizon,
a maximum hit and players who must not be sold. Structured fields may supply the
horizon, hit maximum or protected IDs when a caller already knows them.

The parser understands the first supported question family, such as:

> How can I get Haaland within two Gameweeks without selling Saka, with a
> maximum total hit of eight points?

If a question names no target or asks for a different capability, it receives a
short scope response before the expensive FPL calls begin. If the target name is
ambiguous or the hit limit is not a valid multiple of four, the agent asks one
focused clarification instead of inventing a value.

## Decision boundary

The route planner remains the authority for affordability, free transfers, hits,
deadlines, squad shape and protected players. The evidence service remains the
authority for FPL observations and their provenance. The agent combines these
outputs but does not calculate new transfer legality or future expected returns.

The primary route is the planner's factual feasibility lead: fewest hit points,
earliest target arrival, fewest transfers, highest remaining bank and stable
player IDs. Alternatives are retained from the planner and each is described by
the same concrete route facts. This is a recommendation about the best supported
plan under the manager's stated constraints, not a forecast of points, minutes,
prices or results.

## Grounding boundary

The language model receives only the final status and a list of approved reason
IDs. It may choose which approved reasons to emphasize, but it cannot add a
player, price, statistic, fixture, route or prediction. A changed status,
duplicated reason or unknown reason fails closed with a grounding error.

For non-recommendation results—unsupported question, clarification, target already
owned, no legal route or missing selling prices—the response is deterministic and
does not require a language-model call. A provisional route explicitly asks for
the relevant outgoing selling prices before calling it exact.

## Transparency

Every recommendation report contains:

- the parsed target, protected players, horizon and hit limit
- the full deterministic route report and search bounds
- one recommended route and up to two alternatives
- the evidence report for every material player
- the reason the primary route leads
- comparative alternative reasons
- the strongest objection
- conditions that require a refresh or recalculation
- assumptions and grounded reason records

This makes it possible for the later standalone lab to show what happened at
each stage rather than displaying an unexplained answer.

