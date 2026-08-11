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

The same canonical response is available from the API:

```bash
curl http://localhost:8000/v1/entries/1234567/squad
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
