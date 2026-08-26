# GafferTalk

**Talk to your Fantasy Premier League team.**

GafferTalk is a source-available, AI-powered FPL assistant. Enter an FPL Team ID,
load the current squad, and ask questions such as:

- How can I get Palmer without selling Salah?
- What is my best transfer this week?
- Who should I captain?
- Which player is the weakest part of my team?

The language model handles intent and explanation. FPL data, projections, and
transfer legality are handled by deterministic backend services.

## MVP

The first release is focused on one loop:

```text
Team ID -> team data -> question -> legal, data-driven recommendation
```

Launch-critical capabilities are team loading, player and fixture data, legal
transfer suggestions, target-player transfer routes, basic projections, and
captain recommendations.

## Status

GafferTalk is in initial development for the 2026/27 FPL season. The public MVP
is targeted for August 25–26, after finalized Gameweek 1 squads become publicly
available and before the Gameweek 2 deadline. See the
[MVP roadmap](docs/product/roadmap.md) and GitHub milestones for current scope
and progress.

## Planned architecture

- Web: Next.js and TypeScript
- API and recommendation engine: Python and FastAPI
- Database: PostgreSQL
- AI: tool-calling model for intent extraction and explanation

## Local development

Supported runtimes:

- Node.js 24
- pnpm 11.16
- Python 3.12

Install dependencies:

```bash
pnpm install
python3 -m pip install -e './apps/api[dev]'
```

Run the applications in separate terminals:

```bash
make dev-web
make dev-api
```

The web application runs at `http://localhost:3000`; the API runs at
`http://localhost:8000`, with a health endpoint at `/health`.

Look up a real public FPL Team ID from the terminal:

```bash
make lookup-team TEAM_ID=1234567
python -m gaffertalk_api.cli team 1234567 --json
```

Run the first one-player recommendation engine against live FPL data and the
versioned synthetic squad:

```bash
make recommend-one OUT=Yates
```

The command loads current players, prices, availability and fixtures from FPL,
then prints three ranked legal replacements with their score, remaining bank,
reasons and trade-offs. The versioned demo squad ships with the API at
`apps/api/src/gaffertalk_api/data/synthetic-squad.json`. Before Gameweek 1, the
official performance totals are treated explicitly as a previous-season
baseline rather than current form.

The same canonical response is available from the API:

```bash
curl http://localhost:8000/v1/entries/1234567/squad
```

With both applications running, open `http://localhost:3000/team` to load and
confirm a current team. The completed state continues to `/recommend`, where a
Free user can ask three one-player transfer questions per FPL Gameweek. Three
starter prompts cover the supported recommendation strategies:

- **Best all-rounder:** 45% historical output, 35% next-five fixtures, 20% value
- **Attack the fixtures:** 25% historical output, 60% fixtures, 15% value
- **Stretch the budget:** 25% historical output, 20% fixtures, 55% value

The manager can also write the question in their own words and add one ranked
option to the local plan. The browser updates
the 15-player squad, bank and free-transfer count without an account or
database. This never changes the manager's official FPL team.

Groq interprets the Free question and explains the engine result. Create a local
`.env` from `.env.example` and set `GAFFERTALK_GROQ_API_KEY`. The key is read by
the Python backend only and must never be exposed as a `NEXT_PUBLIC` variable.
The backend persists anonymous per-Gameweek usage in a gitignored local SQLite
file; validation and provider failures do not consume a question.
Named-player questions first pass deterministic ownership, position,
availability, budget and club-limit checks. Invalid or unsupported moves return
an actionable explanation without calling Groq or consuming the allowance.

The first Pro vertical is available at `http://localhost:3000/pro` after the
same team-confirmation journey. It evaluates one named transfer against holding,
waiting, a stronger legal alternative and explicit squad availability risks.
The versioned report shows opportunity cost, next-three planning impact,
structured evidence, freshness, assumptions, change conditions and
deterministic categorical confidence. Groq may select only backend-approved
reason IDs; it cannot add facts or change the verdict. See the
[Pro named-transfer architecture](docs/architecture/pro-named-transfer-research.md).

Whole-squad advice is available at `http://localhost:3000/pro/squad-action`.
A manager can ask for the best current action without entering all 15 selling
prices. GafferTalk requests only a relevant outgoing player's price when needed
to validate a promising route. The versioned policy ranks squad concerns,
compares one-player routes with rolling, tests exact hit cost, and exposes Safe,
Balanced and Aggressive thresholds. See the
[Pro whole-squad action architecture](docs/architecture/pro-squad-action-research.md).

Bounded route research is available at `http://localhost:3000/pro/routes`. A
manager can select a named target, preserve or require the sale of squad players,
reserve bank and search at most two transfers. GafferTalk requests only the relevant
outgoing selling prices before returning an exact route, hit and resulting bank. See
the [Pro route-research architecture](docs/architecture/pro-route-research.md).

The signed-in Pro workspace is available at
`http://localhost:3000/pro/sign-in`. Passwordless email OTP authentication is
provided by Supabase. After signing in, a manager connects a public FPL Team ID,
records any post-deadline changes plus bank and free transfers, and confirms a
versioned planning state. Named-transfer reports and their visible conversation
history are stored account-by-account in PostgreSQL and reopen after sign-out and
sign-in. Start and configure the local services with the
[Supabase Pro workspace runbook](docs/operations/supabase-pro-workspace.md).

The API is prepared for a private Railway staging service while the web
application remains on Cloudflare. See the
[Railway API runbook](docs/operations/railway-api.md) for the monorepo paths,
environment variables, persistent volume and smoke-test checklist. Deployment
still requires owner confirmation and the real-squad Gameweek 1 launch gate.

Recommendation endpoints:

```text
POST /v1/recommendations/transfers
POST /v1/recommendations/conversation
POST /v1/pro/research/named-transfer
POST /v1/pro/research/squad-action
GET /v1/pro/workspace
PUT /v1/pro/workspace/state
POST /v1/pro/workspace/research/named-transfer
GET /v1/free/usage
```

Before the first deadline, a valid entry is returned with an explicit
`not_yet_published` squad status. See the
[team lookup architecture](docs/architecture/team-lookup.md).

Copy `.env.example` to `.env` for local configuration. Never commit `.env`.

Run the local quality checks with:

```bash
make check
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the issue and pull-request workflow.

## License

GafferTalk is source-available under the
[GafferTalk Sustainable Use License](LICENSE.md). It is free for personal,
non-commercial, and internal business use. It may not be sold, offered as a
competing hosted service, or commercially redistributed without separate
permission from the licensor.

This is not an OSI-approved open-source license. Commercial licensing may be
available separately in the future.
