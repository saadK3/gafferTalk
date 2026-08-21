# GafferTalk Pro V1 product requirements document

Status: Approved product direction; ready for implementation planning  
Version: 1.0  
Date: 2026-08-22  
Owner: GafferTalk product owner

## 1. Executive summary

GafferTalk Pro V1 is a persistent transfer decision assistant for Fantasy
Premier League managers. It evaluates whether a manager should buy, hold, wait
or choose an alternative, and it maintains a conditional three-Gameweek plan
based on the manager's confirmed squad and current FPL data.

The core positioning is:

> **Free finds a legal move. Pro investigates whether it is the right move.**

Pro is not a larger chat allowance wrapped around the Free recommendation
engine. Its paid value comes from squad-wide context, skeptical decision
analysis, one- and two-transfer route comparison, persistence, and short-term
planning. It must be willing to recommend holding or rolling even when the
manager asks to buy a named player.

Pro V1 analyzes fixtures across five Gameweeks but prescribes a conditional
plan for the next three. It does not support chip optimization, captaincy,
lineup decisions, automatic transfers, mini-league analysis or arbitrary
long transfer chains.

## 2. Background

The existing Free product supports this journey:

```text
Team ID
  -> latest publicly finalized FPL squad
  -> manager confirms changes, bank and free transfers
  -> manager asks a transfer question
  -> GafferTalk returns legal one-player replacement options
```

The current system already provides:

- Canonical FPL domain models
- Team loading from public FPL endpoints
- Manager confirmation of current planning state
- Deterministic transfer-legality validation
- One-player replacement ranking
- Natural-language intent interpretation and grounded explanation
- A Gameweek-limited Free allowance
- Device-local transfer planning

The relevant existing contracts are documented in:

- `docs/product/free-beta.md`
- `docs/product/current-team-confirmation.md`
- `docs/product/roadmap.md`
- `docs/architecture/conversational-recommendations.md`
- `docs/architecture/one-player-recommendations.md`
- `docs/architecture/transfer-legality.md`

Pro must extend these boundaries rather than create a conflicting second rules
system.

## 3. Problem statement

The Free recommendation flow can identify legal and statistically reasonable
one-player replacements, but it cannot adequately answer the manager's larger
decision:

> Is this transfer worth making for my team, what am I giving up, and what
> should I do afterward?

A useful answer must compare the requested move with holding, waiting and other
squad priorities. It must consider transfer cost, future flexibility, player
and fixture evidence, uncertainty, and the effect across multiple Gameweeks.

Without this decision process, a conversational system risks agreeing with the
manager's premise, overreacting to recent returns, or recommending a locally
attractive transfer while ignoring a more urgent squad problem.

## 4. Product objective

Before an FPL deadline, a Pro manager should be able to use GafferTalk to:

1. Understand the best transfer action to take now.
2. Understand why that action is preferable to holding, waiting or choosing an
   alternative.
3. See the legal and financial consequences of the decision.
4. Understand its effect on the next three Gameweeks.
5. Save a conditional plan that can be reconsidered when new information
   arrives.

The primary job to be done is:

> Help me make a better transfer decision now and preserve a sensible route
> through the next three Gameweeks.

## 5. Goals

Pro V1 must:

- Provide a persistent, team-aware conversational workspace.
- Evaluate buy, hold, wait and alternative actions for named transfers.
- Analyze the manager's whole squad before recommending a move.
- Recommend rolling a transfer when no available move justifies using it.
- Find and validate legal one- and two-transfer routes.
- Evaluate free-transfer use, points hits, remaining bank and future
  flexibility.
- Produce a conditional three-Gameweek plan using five-Gameweek fixture
  context.
- Save conversations, decision reports, watch conditions and the active plan.
- Show evidence, assumptions, source freshness and categorical confidence.
- Remain grounded in canonical data and deterministic legality calculations.
- Preserve the current Free product's usefulness and rules.

## 6. Non-goals

Pro V1 will not:

- Execute or schedule official FPL transfers.
- Request an FPL password, session cookie or private account access.
- Optimize Wildcard, Free Hit, Bench Boost or Triple Captain usage.
- Recommend captains, vice-captains, starting lineups or bench order.
- Analyze mini-league rivals.
- Send deadline or price-change notifications.
- Use an external news or football-data provider as a launch dependency.
- Claim real-time press-conference or predicted-lineup research.
- Generate arbitrary transfer routes longer than two current-Gameweek moves.
- Produce unjustifiably precise expected-points forecasts.
- Use multiple role-playing language-model agents as a product requirement.
- Include public paid checkout in the first private Pro beta.

These exclusions require explicit unsupported responses where relevant; the
system must not silently approximate them with normal-transfer logic.

## 7. Target user

The initial user is an engaged FPL manager who:

- Knows their Team ID and basic squad state.
- Makes decisions weekly but does not want to maintain a complex spreadsheet.
- Wants an informed second opinion rather than an automatic team manager.
- Values explanations, trade-offs and planning flexibility.
- Is comfortable confirming private state that public FPL endpoints cannot see.

V1 does not require the manager to understand advanced statistics. Evidence
must be translated into football and FPL implications.

## 8. Supported V1 questions

The product must recognize and answer five primary question types.

### 8.1 Named transfer decision

Examples:

- "Should I sell Bruno for Odegaard?"
- "Is Saka worth buying for Palmer?"

The system compares making the move, holding, waiting and at least one suitable
alternative when one exists.

### 8.2 Best current action

Examples:

- "What should I do with my transfer this week?"
- "What is the biggest problem in my squad?"

The system evaluates squad priorities and may recommend a transfer, a
two-transfer route or rolling.

### 8.3 Route to a named target

Examples:

- "How can I get Haaland without selling Salah?"
- "Can I afford Odegaard with two transfers?"

The system searches up to two current-Gameweek transfers while respecting
explicit preserve, exclude and budget constraints.

### 8.4 Roll or hit decision

Examples:

- "Should I roll?"
- "Is this worth a four-point hit?"

The system compares the proposed action with doing nothing now and preserving
the transfer for the next Gameweek.

### 8.5 Three-Gameweek plan

Examples:

- "Plan my next three Gameweeks."
- "What should I do now if I want Haaland in GW8?"

The system returns a conditional plan with immediate, planned and watched
actions. It uses five-Gameweek fixture context but does not prescribe more than
three Gameweeks.

Questions outside these categories may receive a brief explanation of current
scope and a suggested supported question. They must not be forced into an
incorrect intent.

## 9. User journey

### 9.1 First Pro session

```text
Sign in
  -> enter Team ID
  -> load latest deadline-finalized squad
  -> review snapshot Gameweek and retrieval time
  -> record transfers made since the deadline
  -> confirm bank and free transfers
  -> confirm captain and vice-captain as squad state only
  -> choose Safe, Balanced or Aggressive risk preference
  -> enter Pro workspace
```

Captain and vice-captain are preserved as team state but are not recommendation
features in V1.

### 9.2 Returning session

The system must:

1. Identify whether a newer finalized FPL snapshot is available.
2. Show the difference between the saved planning state and new snapshot.
3. Ask the manager to confirm changes the public snapshot cannot contain.
4. Mark existing reports and plans stale until reconciliation is complete.
5. Recalculate the active plan after confirmation.

The workspace must never describe a deadline-finalized public squad as private
live state.

### 9.3 Workspace

The Pro workspace must make the following accessible without leaving the
decision flow:

- Current confirmed squad
- Bank and free transfers
- Risk preference
- Active three-Gameweek plan
- Watch conditions
- Conversation history
- Remaining research allowance
- Data and squad-state freshness

The conversation is the input interface. Structured decision reports and the
saved plan are the durable outputs.

## 10. Decision behavior

For a named transfer such as Bruno Fernandes to Odegaard, the system must
consider:

1. Make the requested transfer now.
2. Keep the current player.
3. Wait one Gameweek.
4. Choose a stronger legal alternative, when one exists.
5. Address a more urgent squad problem, when one exists.

The requested move must not receive preferential treatment merely because the
manager named it.

When GafferTalk disagrees, it must still support manager agency. If the manager
chooses to proceed, the system must provide the best validated legal route or
explain why no supported legal route exists.

## 11. Decision report contract

A material transfer or planning question returns a versioned structured report
containing:

| Field | Requirement |
| --- | --- |
| Verdict | `buy`, `hold`, `wait` or `avoid` |
| Recommended action | Concise action for the current deadline |
| Case for | Strongest evidence supporting the requested or recommended move |
| Case against | Strongest evidence against it |
| Best alternative | Best supported alternative, including holding |
| Squad priority | Whether another squad issue is more urgent |
| Opportunity cost | Free transfers, hit, bank, locked funds and flexibility |
| Planning impact | Consequence across the three-Gameweek plan |
| Confidence | `high`, `medium` or `low`, with reasons |
| Change conditions | New facts that would materially alter the verdict |
| Evidence | Structured metrics with source and freshness |
| Legal route | Validated transfer pairs and resulting planning state |
| Assumptions | Missing, user-supplied or uncertain state used in the answer |

The response may render a shorter conversational summary first, but the full
structured report must remain available for inspection and saving.

The language model may explain or synthesize only the structured players,
routes and evidence supplied by GafferTalk services. It must not introduce an
unvalidated route or unsupported factual claim.

## 12. Planning contract

### 12.1 Horizon

- Fixture and player context: next five Gameweeks
- Prescriptive plan: current Gameweek plus the following two Gameweeks
- Maximum current-Gameweek route: two transfers
- Maximum planned moves across the three-Gameweek horizon: three transfers

### 12.2 Plan action types

Every plan item must use one of these states:

- **Commit now:** recommended before the current deadline
- **Plan:** likely future action based on current information
- **Watch:** condition that must be observed before acting
- **Alternative:** action to use if a watch condition changes

### 12.3 Plan lifecycle

A plan must record:

- Squad-state version used
- FPL data retrieval time
- Creation and last-recalculation times
- Gameweek horizon
- Proposed transfers and resulting financial state
- Conditions and alternatives
- Confidence and assumptions
- Status: active, stale, completed, superseded or abandoned

A plan becomes stale when:

- A new FPL snapshot is published.
- The manager records a transfer outside the plan.
- Bank, free transfers or a required selling price changes.
- A referenced player becomes unavailable.
- Relevant fixture scheduling changes.
- Its current deadline passes.

The system must show stale status and request reconciliation or recalculation;
it must not silently treat the old plan as current.

## 13. Risk preference

Each Pro profile has one required preference:

| Preference | Decision behavior |
| --- | --- |
| Safe | Prioritize availability, stable minutes, proven role and flexibility |
| Balanced | Balance reliability, underlying performance and upside |
| Aggressive | Accept more rotation, differential and short-term upside risk |

The default is Balanced. Risk preference may affect versioned deterministic
weights or documented decision policy, but it must never bypass transfer
legality or availability safeguards.

V1 will not maintain inferred personality profiles, favorite-player profiles,
rank targets or hidden behavioral preferences. Constraints stated in a question
apply to that decision and may be saved only when the manager explicitly adds
them to the plan.

## 14. Confidence contract

Confidence must be categorical rather than a model-invented percentage.

It is derived from documented structured factors including:

- Data completeness and freshness
- Availability certainty
- Recent starts and minutes reliability
- Current-season sample size
- Separation between the leading options
- Dependence on user-confirmed selling price or missing state
- Sensitivity to injury, role or lineup assumptions

Every confidence level must include at least one reason. Low confidence does
not prevent a recommendation, but it must make the principal uncertainty and a
relevant watch condition explicit.

The calculation must be versioned and testable. The language model may explain
the result but may not select or alter the confidence level.

## 15. Data requirements

### 15.1 Manager state

Pro V1 requires:

- Team ID and public entry summary
- Latest finalized 15-player squad
- Starting lineup and bench state for context
- Captain and vice-captain for state reconciliation
- Confirmed bank and free transfers
- Selling prices for outgoing players when exact legality requires them
- Recorded transfers made after the public snapshot
- Saved plan and explicit constraints
- Risk preference

### 15.2 Player and team evidence

V1 should use FPL data already available through the existing integration or an
expanded version of it:

- Minutes and starts
- Goals and assists
- FPL points and bonus
- Position-specific returns
- Current price and selection percentage
- Transfer movement where available
- FPL-provided expected goals, assists and goal involvement
- Per-Gameweek player history
- Current-season and recent-period summaries
- Deterministically derived per-90 and per-start metrics
- Team attacking and defensive evidence derivable from available data
- Current availability status and FPL player news

### 15.3 Fixture evidence

V1 requires:

- Next five scheduled fixtures
- Home and away status
- FPL fixture difficulty
- Blank and double Gameweek representation
- Fixture congestion indicators derivable from kickoff times
- Started, finished, postponed and rescheduled fixture handling

### 15.4 Provenance

Every decision report must distinguish:

- Observed FPL data
- Deterministically derived metrics
- User-supplied planning state
- Unavailable information

Displayed evidence must include a human-readable freshness indicator. Internal
records must retain retrieval timestamps and source identifiers.

### 15.5 External data

No external football-data or news provider is required for V1. GafferTalk must
not claim knowledge of predicted lineups, live press conferences, tactical role
changes or breaking news unless those claims are present in an approved source.

External enrichment may be proposed after a documented coverage benchmark. A
paid launch may not use external data until licensing, attribution,
redistribution and commercial-use requirements have been reviewed.

## 16. Deterministic responsibilities

Deterministic backend services remain authoritative for:

- Player identity and catalogue membership
- Squad composition and club limits
- Transfer legality
- Prices, confirmed selling prices and bank calculations
- Free-transfer use and points hits
- Candidate generation and route enumeration
- Derived numerical metrics
- Scenario financial state
- Plan-state transitions and staleness
- Confidence classification
- Versioned scoring or ranking calculations
- Research allowance accounting

Language models may:

- Interpret supported question intent and explicit constraints.
- Select among backend-supplied analysis modes.
- Synthesize a qualitative opinion from structured, validated scenarios.
- Explain evidence, trade-offs, uncertainty and plan conditions.

Language models may not:

- Invent or resolve player IDs independently.
- Generate a route that was not validated by the backend.
- Calculate legality, prices, hits or remaining bank.
- Introduce factual statistics not present in the evidence package.
- Change deterministic ordering while presenting it as engine output.
- Claim access to private FPL state or unsupported external research.

## 17. Reasoning architecture

Pro V1 should use an orchestrated pipeline rather than a collection of
role-playing agents:

```text
Manager question
  -> deterministic preflight and player resolution
  -> intent and constraint interpretation
  -> canonical squad and evidence package
  -> squad-priority analysis
  -> scenario and transfer-route generation
  -> risk and opportunity-cost checks
  -> deterministic legality and confidence validation
  -> grounded synthesis
  -> persisted decision report and optional plan update
```

An additional critique pass may be introduced if evaluations demonstrate that
it improves decision quality enough to justify its latency and cost. Multiple
specialist LLM agents are not required for V1 and must not be added without an
evaluation showing measurable benefit.

## 18. Persistence requirements

The server must persist:

- User account and Pro entitlement
- Team ID and confirmed planning-state versions
- Risk preference
- Conversation metadata and user-visible messages
- Versioned decision reports
- Active and historical plans
- Watch conditions and explicit saved constraints
- Research-allowance ledger
- Consent, creation and update timestamps required for account management

The system should not persist unless operationally required:

- Hidden chain-of-thought or private model reasoning
- Complete raw model-provider payloads
- Reconstructible temporary candidate sets
- FPL entry payloads containing unnecessary manager identity fields
- Secrets, FPL credentials or session cookies

Users must be able to sign out and request deletion of their stored Pro data.
Logging and telemetry must avoid raw conversations and manager-identifying FPL
payloads by default.

The exact authentication, database and payment vendors are implementation
decisions, not product requirements. Data ownership and authorization must be
enforced server-side.

## 19. Free and Pro entitlements

### Free

- Three successful questions per browser per Gameweek
- One-player replacement recommendations
- Existing balanced, fixture-first and value-first strategies
- Legal options and grounded explanation
- Device-local planning

### Pro V1

- Signed-in persistent workspace
- Five supported decision question types
- Buy, hold, wait and alternative comparison
- Squad-priority and roll analysis
- Legal two-transfer routes
- Hit and opportunity-cost analysis
- Conditional three-Gameweek planning
- Saved reports, conversations, plans and watch conditions
- Risk preference
- Explicit evidence, freshness and confidence
- Twenty successful research runs per Gameweek during private beta

A Pro research run is consumed only when the system loads or refreshes evidence,
evaluates scenarios and produces a new decision report. The following do not
consume a run:

- Validation failures
- Provider or upstream failures
- Reopening a saved report
- Lightweight follow-ups that can be answered entirely from the current report
- Required clarification of missing planning state

Allowance must be enforced server-side. The commercial fair-use limit remains
configurable and will be set after private-beta cost and usage measurement.

## 20. Error and missing-state behavior

The system must return an actionable, non-success state when:

- A public squad is not yet available.
- The saved squad has not been reconciled with a newer snapshot.
- Bank or free-transfer state is missing.
- A necessary selling price is unknown.
- A named player is unknown or ambiguous.
- A requested route violates position, budget, ownership or club limits.
- A chip scenario is detected.
- Current FPL data is unavailable or malformed.
- The language-model provider is unavailable.
- The research allowance is exhausted.
- Evidence is too incomplete to support the requested comparison.

Failures before a completed report must not consume allowance. Partial provider
failure must not authorize a fallback answer containing invented claims.

## 21. Functional requirements

### PRO-1 — Account-bound workspace

A signed-in Pro user can connect a Team ID and access only their own persisted
squad state, conversations, reports and plans.

### PRO-2 — Squad reconciliation

The user can reconcile a saved state with the newest public snapshot and confirm
private changes, bank and free transfers before new advice is produced.

### PRO-3 — Supported intent handling

The system recognizes the five supported question types, resolves named players
conservatively and requests only missing information necessary to proceed.

### PRO-4 — Squad-wide comparison

Named transfer evaluation includes hold, wait, alternative and squad-priority
scenarios rather than evaluating only the requested incoming player.

### PRO-5 — Legal route search

The system generates and ranks legal routes containing no more than two
current-Gameweek transfers and returns their exact financial and hit effects.

### PRO-6 — Rolling recommendation

The system may explicitly recommend rolling a transfer when supported candidate
moves do not justify their opportunity cost.

### PRO-7 — Decision report

Every completed research run produces a versioned report satisfying the
contract in section 11.

### PRO-8 — Conditional plan

A user can save an accepted report into an active three-Gameweek plan containing
commit, plan, watch and alternative actions.

### PRO-9 — Plan freshness

The system marks plans stale and requests reconciliation or recalculation when
a defined staleness event occurs.

### PRO-10 — Evidence and confidence

Every material recommendation shows evidence freshness, provenance, assumptions
and a deterministic categorical confidence level.

### PRO-11 — Manager override

When the manager chooses a legal move contrary to the verdict, the system
provides the best supported route without falsely changing its prior analysis.

### PRO-12 — Persistence

The user can leave and return to their latest confirmed squad, conversations,
reports and active plan from another authenticated session.

### PRO-13 — Allowance enforcement

The backend reserves, consumes and refunds research allowance consistently and
does not rely on browser state as the authority.

### PRO-14 — Unsupported scope

Chip, captaincy, lineup, rival and automatic-transfer requests return explicit
scope guidance and do not produce disguised normal-transfer advice.

### PRO-15 — Account data controls

The user can sign out and initiate deletion of stored account data. One user
cannot access another user's team state or conversation resources.

## 22. Acceptance criteria

Pro V1 is functionally complete when:

1. A signed-in beta user can connect and reconcile a real Team ID without
   exposing FPL credentials.
2. Each of the five supported question types completes end to end against real
   post-deadline squads.
3. Every named-transfer report compares the requested move with holding and
   waiting; a legal alternative is included when one exists.
4. The system can identify a more urgent squad issue and recommend rolling.
5. One- and two-transfer routes satisfy the canonical legality suite with
   correct bank, free-transfer and hit calculations.
6. A report cannot contain a player, price, fixture, statistic or route absent
   from its structured evidence and validated scenarios.
7. Confidence is produced by the versioned deterministic policy and includes a
   reason.
8. A report can be saved as a conditional three-Gameweek plan.
9. Plans become visibly stale after all specified staleness events.
10. New advice is blocked until materially stale squad state is reconciled.
11. Conversations, reports and plans persist across authenticated sessions and
    remain isolated between users.
12. Failed requests and required clarifications do not consume research
    allowance.
13. Unsupported chip, captaincy, lineup and rival questions fail explicitly.
14. Data source and freshness are visible in every material report.
15. Provider failure never results in an ungrounded fallback recommendation.

## 23. Quality gates

The private beta may begin only when:

- The deterministic scenario suite has no known illegal route failures.
- Grounding tests reject every fixture containing an invented player, price,
  statistic or transfer route.
- Golden product scenarios cover every supported question type, risk preference
  and major missing-state path.
- Identical structured inputs produce the same legal candidates, financial
  results, confidence and ranking regardless of language-model output.
- The complete onboarding, reconciliation, conversation, report-saving and plan
  refresh journey passes on desktop and mobile.
- Authorization tests demonstrate that account-scoped resources cannot be read
  or changed by another user.
- Usage and provider cost per completed research run can be measured.
- Error telemetry captures failures without recording raw private conversation
  content or manager PII by default.

## 24. Success metrics

### Correctness and trust

- Zero known illegal recommendations in beta and canonical test scenarios.
- Zero accepted ungrounded factual claims in the launch evaluation set.
- At least 90% of beta reports are rated understandable by their manager.
- At least 80% of interviewed beta managers can identify the recommended
  action, principal trade-off and change condition without assistance.

### Product value

- At least 60% of activated beta users complete a second research run in a
  later session or Gameweek.
- At least 40% of completed planning reports are saved into an active plan.
- At least 50% of beta users report that Pro changed, confirmed or clarified a
  real transfer decision.

### Reliability and cost

- At least 98% of valid research requests complete successfully, excluding
  confirmed upstream FPL outages.
- Failed requests do not consume allowance.
- Median and high-percentile model cost and latency per research run are known
  before paid launch; commercial limits and pricing must be reviewed against
  those measurements.

These are initial private-beta targets and may be revised from observed usage.
Correctness and grounding gates cannot be relaxed merely to improve engagement.

## 25. Rollout plan

### Phase 1 — Contracts and evaluation fixtures

- Freeze versioned decision-report, evidence, confidence and plan contracts.
- Create canonical named-transfer, roll, hit, route and planning scenarios.
- Establish grounding and recommendation-quality evaluations.

### Phase 2 — Analytics foundation

- Expand FPL ingestion for per-Gameweek history and required evidence.
- Add versioned derived metrics and five-Gameweek fixture context.
- Implement deterministic confidence and squad-priority inputs.

### Phase 3 — Single-transfer Pro slice

- Deliver buy, hold, wait and alternative analysis for named one-player moves.
- Validate the full decision-report pipeline before persistence or two-transfer
  breadth obscures recommendation quality.

### Phase 4 — Squad priority and roll

- Evaluate the whole squad.
- Recommend a more urgent problem or rolling when appropriate.

### Phase 5 — Two-transfer routes

- Add bounded route generation, hit analysis and future-flexibility evidence.

### Phase 6 — Three-Gameweek plans

- Add conditional plan generation, saving, staleness and recalculation.

### Phase 7 — Accounts and Pro workspace

- Add authentication, account isolation and persistence.
- Build the conversational workspace around reports and the active plan.
- Add research allowance enforcement and account data controls.

### Phase 8 — Private Pro beta

- Grant Pro entitlement manually or through a non-public beta mechanism.
- Validate usefulness, reliability, latency and cost with real managers.
- Resolve P0 correctness, authorization and grounding failures before expansion.

### Phase 9 — Paid-launch readiness

- Set fair-use limits and pricing from measured costs and usage.
- Complete commercial data-use and product-policy review.
- Add billing and entitlement lifecycle as a separately scoped launch feature.
- Re-run security, privacy, accessibility and end-to-end launch checks.

## 26. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Pro becomes an unfocused general FPL chatbot | Enforce five supported question types and explicit non-goals |
| Model agrees with the manager by default | Require hold, wait, alternative and squad-priority scenarios |
| Fabricated facts or routes | Structured evidence, deterministic validation and grounding gates |
| Multi-Gameweek plans become stale quickly | Conditional actions, timestamps, staleness and recalculation |
| Missing private squad state corrupts legality | Reconciliation and just-in-time selling-price confirmation |
| Route search becomes expensive or opaque | Cap current routes at two transfers and plans at three moves |
| Early-season samples create false confidence | Versioned confidence policy and explicit sample-size uncertainty |
| External data delays launch | Use current FPL data first and benchmark enrichment separately |
| Model cost makes Pro unsustainable | Meter research runs, cache evidence and measure cost before pricing |
| Persistent data increases privacy risk | Minimize stored payloads, isolate accounts and support deletion |
| Free is weakened to manufacture paid value | Keep existing Free capabilities and differentiate on depth and persistence |

## 27. Dependencies

- Stable public FPL catalogue, fixture, player-history and squad endpoints
- Existing canonical FPL models and adapter boundary
- Existing transfer-legality service and scenario suite
- A production-capable database for account-scoped persistence
- Authentication and entitlement enforcement
- A server-side language-model provider integration
- Monitoring for application, upstream, model and grounding failures
- Privacy, terms and commercial-data review before public paid launch

Vendor selection for authentication, database, model provider, hosting and
billing belongs in architecture decision records or implementation issues.

## 28. Definition of done

Pro V1 is done when all functional acceptance criteria and quality gates pass,
the five supported question types work against real reconciled squads, plans
persist and become stale correctly, recommendation evidence is grounded, and a
private beta demonstrates that managers understand and value the resulting
decisions.

Completion of the core V1 does not itself authorize a public paid launch. Paid
launch additionally requires approved pricing and fair-use limits, billing and
entitlement lifecycle, commercial data-use review, and the repository's normal
deployment confirmation.

## 29. Follow-up documents

After approval of this PRD, create:

1. A Pro V1 architecture and data-flow document.
2. Versioned API and domain contracts for evidence, reports and plans.
3. A recommendation-quality evaluation specification.
4. A persistence and authorization model.
5. A milestone-aligned GitHub issue roadmap with acceptance criteria.

The earlier `docs/product/pro-v1-discussion-brief.md` remains useful as the
decision history, but this PRD becomes the source of truth for Pro V1 scope.
