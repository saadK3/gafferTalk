# Research page

The personal research page is available at `/research`. It uses the confirmed
browser state created by `/research/team`, so no account or database is needed
for the first personal version.

## User flow

1. Load a public FPL Team ID at `/research/team`.
2. Confirm any post-deadline changes, current bank and free transfers.
3. Open the research assistant and ask a free-form question or choose a template.
4. Read the recommended plan, alternatives, labelled facts and assumptions.
5. If exact legality depends on selling prices, enter the prices shown by FPL and
   retry the same question. Prices are kept for the current browser session.

The frontend calls `POST /v1/agent/conversation`. The response's
`selling_price_requests` array is rendered directly; the UI never has to parse
the assistant's prose to discover a missing price. A current FPL price is shown
only as an upper-bound reference, never as the manager's actual selling price.

## Local check

From the repository root, run the API and web app in separate terminals:

```bash
make dev-api
pnpm dev:web
```

Then open `http://localhost:3000/research/team` and continue to
`http://localhost:3000/research`. Set `NEXT_PUBLIC_API_BASE_URL` if the API is
not running on port 8000.

This slice supports the current Gameweek and the bounded one- or two-Gameweek
research capabilities already exposed by the API. Longer planning windows and
external football news remain later work.
