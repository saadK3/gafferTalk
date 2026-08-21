# GafferTalk Pro V1 discussion brief

Status: Superseded as the scope authority by `docs/product/pro-v1-prd.md`. This
brief remains the decision history and original discussion prompt.

Use this brief to start a product and engineering discussion with Codex. The
objective is to challenge the proposal, narrow it to a coherent V1, and then
turn the agreed scope into a PRD and implementation plan. Do not begin
implementation until the important product decisions and acceptance criteria
have been agreed.

## Product context

GafferTalk is an AI-powered Fantasy Premier League assistant with the promise:

> Talk to your FPL team.

The current Free product supports this loop:

```text
Team ID
  -> latest publicly finalized FPL squad
  -> manager confirms changes, bank and free transfers
  -> manager asks a transfer question
  -> GafferTalk returns legal one-player replacement options
```

The backend already separates language-model interpretation and explanation
from deterministic FPL data, ranking and transfer-legality services. The Free
version currently offers three successful questions per browser per Gameweek,
three simple scoring strategies, one-player transfers and device-local
planning.

Important existing constraints:

- A public Team ID reveals the latest deadline-finalized squad, not unpublished
  private team state.
- The manager must confirm changes made since that snapshot, current bank and
  free transfers.
- Exact selling prices must be confirmed when transfer legality depends on
  them.
- GafferTalk does not request an FPL password and does not execute transfers.
- Transfer legality and numerical calculations must remain deterministic.
- The language model must not invent players, prices, statistics, fixtures or
  legal routes.

Relevant repository documents include:

- `docs/product/free-beta.md`
- `docs/product/current-team-confirmation.md`
- `docs/product/roadmap.md`
- `docs/architecture/conversational-recommendations.md`
- `docs/architecture/one-player-recommendations.md`
- `docs/architecture/transfer-legality.md`

## Why Pro should exist

The Free product can answer:

> What is a legal and statistically reasonable one-player transfer?

Pro should answer:

> Is this actually the right decision for my team, what am I giving up, and
> what should I do over the next few Gameweeks?

The working positioning is:

> **Free finds a legal move. Pro investigates whether it is the right move.**

Pro should not merely provide more messages, more statistics or longer prose.
Its paid value should come from deeper research, squad-wide reasoning,
multi-step planning, persistence and a willingness to disagree with the
manager.

## Desired user journey

The proposed journey is:

```text
Sign in
  -> enter or connect FPL Team ID
  -> load the latest public squad snapshot
  -> reconcile transfers made since the deadline
  -> confirm bank, free transfers, captaincy and relevant chip state
  -> enter a persistent team workspace
  -> discuss decisions and maintain a rolling plan
```

The workspace is envisioned as a team-aware chat accompanied by the manager's
current squad, bank, free transfers, saved plan, watchlist and a three-to-five
Gameweek horizon. Conversation and planning state should persist across
sessions for a signed-in Pro user.

After each deadline, the manager should reconcile the saved state with the
newest public FPL snapshot rather than GafferTalk pretending it can see private
unpublished changes.

## Example of the intended behavior

Suppose the manager says:

> I want to replace Bruno Fernandes with Odegaard.

GafferTalk should not assume that completing the requested move is the goal. It
should compare at least:

1. Make Bruno to Odegaard now.
2. Keep Bruno.
3. Select a stronger alternative.
4. Wait one Gameweek.

The response should explain the case for and against the requested transfer,
consider problems elsewhere in the squad, quantify the cost of using a free
transfer or taking a hit, and assess how the decision affects the next three to
five Gameweeks.

If the recommendation is to hold but the manager still wants the transfer,
GafferTalk should respect that preference and provide the best legal route. It
should be opinionated without becoming controlling.

## Candidate Pro V1 capabilities

These are candidates to debate and prioritize, not automatically approved V1
scope:

- Persistent account, squad state, conversations and plans
- A team-aware conversational workspace
- Buy versus hold versus wait versus alternative comparisons
- Squad weakness and priority analysis
- Multi-transfer route generation
- Three-to-five Gameweek rolling plans
- Transfer-hit and opportunity-cost analysis
- Captaincy and starting-lineup advice
- Saved watchlists and conditional decisions
- Richer player, team, opponent and fixture research
- Explicit confidence, assumptions, sources and data freshness
- A substantially larger but still controlled question allowance

Possible follow-on capabilities include Wildcard and Free Hit optimization,
mini-league rival analysis, deadline notifications and automatic weekly plan
refreshes. These should not enter V1 merely because they are attractive.

GafferTalk must not automatically execute official FPL transfers in V1.

## Proposed answer contract

For a material transfer or planning question, consider returning a structured
decision report containing:

- **Verdict:** buy, hold, wait or avoid
- **Recommended action:** what to do now
- **Case for:** why the requested move could work
- **Case against:** why it may be a mistake
- **Best alternative:** including holding when appropriate
- **Opportunity cost:** transfer, hit, budget and other squad priorities
- **Planning impact:** effect across the chosen Gameweek horizon
- **Risk and confidence:** uncertainty around minutes, role, injuries and data
- **Change conditions:** new information that would alter the verdict
- **Evidence:** supporting metrics with source and freshness
- **Legal route:** the exact route if the manager chooses to proceed

The final UX does not have to display every section for every lightweight
question. Part of the V1 discussion is deciding when a full decision report is
required and when a shorter conversational response is enough.

## Rolling planning model

A multi-Gameweek plan should not claim that a fixed sequence will remain
optimal as new information arrives. Proposed plan actions should distinguish:

- **Commit now:** an action recommended for the current deadline
- **Plan:** a likely future action based on current information
- **Watch:** a condition such as fitness, role, price or fixture news
- **Alternative:** what to do if the watch condition changes

Example:

| Gameweek | Current recommendation | Condition or alternative |
| --- | --- | --- |
| GW6 | Roll the transfer | Sell Bruno if an injury is confirmed |
| GW7 | Bruno to Odegaard | Choose the alternative if Odegaard loses set pieces |
| GW8 | Upgrade a defender | Delay if a double Gameweek is announced |

Plans should be recalculated after deadlines and material changes rather than
silently preserved as if they were still current.

## Reasoning and system architecture

"Multi-agentic" is a possible implementation approach, not a user-facing
requirement by itself. The goal is higher-quality, auditable reasoning.

A candidate pipeline is:

```text
Manager question
  -> intent and context orchestration
  -> squad-needs analysis
  -> player and fixture comparison
  -> transfer-route or Gameweek-plan search
  -> risk and opportunity-cost critique
  -> deterministic legality validation
  -> grounded final synthesis
```

Some analyses may run independently or in parallel. However, avoid creating
multiple role-playing LLM agents unless evaluation shows that they materially
improve recommendation quality. Deterministic services and structured outputs
should do as much work as possible.

Before returning a recommendation, the system should check questions such as:

- Was holding genuinely considered?
- Is another squad problem more urgent?
- Is the proposed improvement worth a points hit?
- Are recent results being overweighted relative to underlying performance?
- Does the route preserve useful budget and future flexibility?
- Are expected minutes, tactical role or injury assumptions uncertain?
- Is every numerical or factual claim present in trusted input data?

The product should produce an informed opinion rather than fake precision. A
well-supported qualitative verdict is preferable to an unjustifiably precise
expected-points number.

## Data required

The analysis may need four context layers:

### Manager context

- Current 15-player squad and starting lineup
- Bank, free transfers and relevant selling prices
- Captain and vice-captain
- Active or intended chips where supported
- Current injuries and other urgent squad problems
- Saved plan, preferences and prior decisions

### Player performance

- Minutes, starts, goals and assists
- FPL points, bonus and position-specific returns
- Current price, ownership and transfer movement
- Recent, season-long and previous-season baselines

### Underlying performance

- Expected goals, assists and goal involvement
- Useful per-90 and per-start derivatives
- Shots, shots in the box, chances and big chances where legally available
- Team attacking and defensive strength

### Context and risk

- Next three-to-five fixtures and home/away status
- Blank and double Gameweeks and fixture congestion
- Availability, injury and suspension information
- Expected minutes, starting and rotation risk
- Penalty, corner and free-kick roles
- Tactical-role or lineup changes where reliably sourced

The current FPL feeds already provide a useful portion of this information.
V1 should first inventory and use the official-site data already available,
including per-Gameweek player history, before paying for enrichment.

An external football-data or news provider should be selected only after a
small coverage benchmark proves that it materially improves decisions. Data
licensing, attribution, redistribution and commercial-use rights must be
reviewed before a paid Pro launch.

## Likely technical gaps

Compared with the current Free implementation, Pro is likely to require:

- Authentication and account ownership
- Server-side persistence for squads, reconciliations, conversations and plans
- Versioned conversation and recommendation schemas
- Historical and per-Gameweek analytical data storage
- Expanded FPL ingestion and derived metrics
- Multi-transfer and multi-Gameweek search
- Research/news ingestion if approved
- A planning state machine with conditions and revisions
- Usage, cost and entitlement enforcement
- Recommendation-quality evaluations and grounded-claim checks
- Product telemetry that avoids logging private manager data unnecessarily

These gaps should be sequenced rather than implemented as one large system.

## Questions the V1 discussion must settle

Challenge the proposal and recommend explicit decisions for each question:

1. What is the single paid job-to-be-done for Pro V1?
2. Which three-to-five question types must V1 answer exceptionally well?
3. Is the central artifact a chat response, a decision report, a rolling plan,
   or a combination with one clearly primary?
4. Is captaincy and lineup advice in V1, or should V1 focus entirely on
   transfer decisions and planning?
5. Does V1 support arbitrary multi-transfer routes, or cap route depth and
   Gameweek horizon?
6. Should chip planning be excluded, partially supported, or included for one
   named chip?
7. Which user preferences are essential: risk appetite, planning horizon,
   favorite players, team value preservation or rank goals?
8. What information must be persistent, and what can remain ephemeral?
9. Which claims can be supported with existing FPL data, and which genuinely
   require an external provider?
10. What is the minimum acceptable research freshness around injury and lineup
    news?
11. How should confidence be calculated and communicated without false
    precision?
12. What belongs in Free versus Pro without deliberately weakening Free?
13. What fair-use limit and cost controls are needed for Pro?
14. Which recommendation-quality evaluations must pass before launch?
15. What are the smallest implementation milestones that deliver testable user
    value?

## Requested output from Codex

Inspect the repository and then facilitate a critical product discussion. Do
not simply agree with this brief. Identify scope risks, missing assumptions,
data limitations and places where the proposed experience may be too broad.

Produce:

1. A concise restatement of the strongest Pro value proposition.
2. A recommended V1 feature boundary and explicit non-goals.
3. The three-to-five supported V1 question types.
4. A proposed user journey and answer contract.
5. A recommendation on whether true multi-agent orchestration is justified for
   V1.
6. The minimum data and persistence architecture required.
7. Open product decisions that require owner input, with a recommendation for
   each.
8. A phased implementation outline, but no implementation yet.
9. Draft success metrics and acceptance criteria.

Once the owner and Codex agree on those decisions, convert the result into a
formal Pro V1 PRD and a GitHub issue roadmap that follows the repository's
existing development workflow.
