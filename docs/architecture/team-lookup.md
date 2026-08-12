# Team lookup architecture

Issues: #3, #4, #5

## Boundary

The Team ID lookup slice converts unversioned public FPL JSON into validated,
immutable GafferTalk domain data.

```text
CLI, GET /v1/entries/{team_id}/squad, or the `/team` web flow
  -> TeamLoader
  -> FplClient
  -> public FPL JSON endpoints
  -> upstream Pydantic schemas
  -> mapper
  -> canonical domain models
  -> terminal or JSON response
```

Raw upstream payloads do not cross the integration boundary. Additive FPL
fields are ignored, but missing, malformed, or contradictory required fields
fail closed.

## Public endpoints

The slice currently consumes:

- `/bootstrap-static/`
- `/fixtures/`
- `/element-summary/{player_id}/`
- `/entry/{team_id}/`
- `/entry/{team_id}/history/`
- `/entry/{team_id}/transfers/`
- `/entry/{team_id}/event/{gameweek}/picks/`

Global catalogue and fixture calls use a five-minute process-local cache.
Player summaries use a one-hour cache. Entry and picks calls use short caches.
The cache coalesces concurrent requests for the same key.

No Redis or database is required for this slice.

The web confirmation flow also uses `GET /v1/players?position={position}&query={query}`
to search canonical current players when a manager records a transfer made
after the deadline. Search requires an explicit position and at least two query
characters; it is not a recommendation endpoint.

## Availability behavior

A valid Team ID and a published squad are separate facts.

Before the first deadline, a valid entry returns:

```json
{
  "availability": {
    "status": "not_yet_published"
  },
  "snapshot": null
}
```

After a deadline, the loader checks deadline-passed Gameweeks newest first and
uses the newest publicly available picks response. A 404 for picks does not turn
the Team ID into an invalid ID.

## Error contract

| Condition | CLI exit | HTTP status |
| --- | ---: | ---: |
| Valid entry, no published picks | 0 | 200 |
| Invalid Team ID | 2 | 404 |
| FPL timeout | 3 | 504 |
| FPL unavailable/rejected | 3 | 503 |
| Invalid FPL response | 3 | 502 |

The application does not log domain objects or upstream entry payloads, which
prevents manager identity from being copied into ordinary request logs.

See [current-team confirmation](../product/current-team-confirmation.md) for the
observed-versus-user-supplied state boundary after lookup.

## Provisional post-deadline contract

The successful 2026/27 picks response cannot be observed until the GW1 deadline.
The adapter is implemented against the established response shape and synthetic
sanitized tests. Issue #16 must revalidate it immediately after the deadline.
