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

GafferTalk is in initial development for the 2026/27 FPL season. Work is
planned and tracked through GitHub Issues and milestones.

## Planned architecture

- Web: Next.js and TypeScript
- API and recommendation engine: Python and FastAPI
- Database: PostgreSQL
- AI: tool-calling model for intent extraction and explanation

Detailed development and self-hosting instructions will be added as the first
vertical slice is implemented.

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
