# General research agent

Slice 4 turns the named-target loop into one controlled entry point for several
valid FPL research questions. The endpoint is:

POST /v1/agent/research

## Question routing

    Question + optional manager state
      -> capability preflight (no FPL calls for unsupported or incomplete team questions)
      -> historical alternatives
      -> named-target transfer route
      -> budget-release route
      -> hold-versus-transfer squad action
      -> squad concerns and priorities
      -> common transparent report
      -> optional grounded Groq wording

The router recognises capability from the question rather than requiring the
caller to select a workflow. A question outside the supported FPL scope gets a
short redirect. A decision that depends on squad state asks for the missing
15-player squad, bank and free transfers. Historical alternatives do not require
that private planning state.

## Supported capabilities

- **Named target transfer:** reuse the bounded multi-Gameweek route planner.
- **Budget release:** answer how to free funds for a named target using the same
  validated route planner.
- **Historical alternatives:** compare available players by observed season
  points, minutes and starts, with recent minutes reliability calculated from
  per-Gameweek history. A position or named comparison subject is enough; bank
  and selling prices are not required.
- **Hold versus transfer:** reuse the whole-squad action report to compare a
  legal move with rolling under the selected risk policy.
- **Squad concerns:** expose the ranked availability, minutes and upgrade
  concerns already documented by the whole-squad decision service.

## Report boundary

Every capability returns the same inspectable envelope:

- capability and status
- one recommended action and up to two alternatives
- observed facts
- labelled calculations
- a separate opinion
- strongest objection and change conditions
- assumptions and grounded reason IDs
- the detailed deterministic source report where one exists

Points-wise and minutes-wise comparisons mean historical FPL observations. The
agent does not forecast future points, minutes, prices, selection or results.
The route and squad-action engines remain authoritative for legality, money,
free transfers and ranking policy.

Groq receives only the final capability, status and approved reason IDs. It may
choose which reasons to emphasise, but a changed status, unknown reason or
invented claim fails closed.
