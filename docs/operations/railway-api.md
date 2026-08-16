# Railway API deployment

Issue: #37

This runbook prepares the Python API for a private Railway staging deployment.
It does not authorize a production deployment or public beta launch.

## Intended topology

- `gaffertalk.com`: Next.js web application on Cloudflare Workers
- Railway service: FastAPI backend from this repository
- Staging API: Railway-generated domain initially
- Production API: `api.gaffertalk.com` after staging verification
- Persistent usage store: one Railway volume mounted at `/data`

The SQLite quota store is suitable only while the API runs as one replica. Move
the allowance store to PostgreSQL before horizontally scaling the API.

## Repository configuration

Railway service settings must use:

- Root Directory: `/apps/api`
- Config File Path: `/apps/api/railway.json`
- Healthcheck: `/health` (provided by config as code)
- Public networking: generate a Railway domain for staging

`apps/api/railway.json` uses Railpack and starts Uvicorn on Railway's supplied
`$PORT`. Railway waits for `/health` before routing traffic and restarts a failed
process up to ten times.

## Required Railway variables

Set these in the staging service. Values marked secret must be entered in the
Railway dashboard and must never be committed.

| Variable | Staging value | Secret |
| --- | --- | --- |
| `GAFFERTALK_ENVIRONMENT` | `staging` | No |
| `GAFFERTALK_CORS_ORIGINS` | Exact HTTPS Cloudflare preview origin | No |
| `GAFFERTALK_GROQ_API_KEY` | Existing Groq server key | Yes |
| `GAFFERTALK_GROQ_MODEL` | `openai/gpt-oss-20b` | No |
| `GAFFERTALK_FREE_QUESTION_LIMIT` | `3` | No |
| `GAFFERTALK_FREE_USAGE_DATABASE_PATH` | `/data/gaffertalk.sqlite3` | No |

The existing FPL URL, retry and timeout defaults are appropriate initially.
Railway provides `PORT`; do not create it manually.

## Persistent volume

Attach one Railway volume to the API service and set its mount path to `/data`.
The application creates the SQLite file on startup. A relative database path is
rejected in staging and production so quota records cannot silently move back to
ephemeral application storage.

## Staging deployment checklist

1. Confirm CI is green on the deployment-preparation pull request.
2. Create a Railway project and an API service from `saadK3/gafferTalk`.
3. Configure the root and config-file paths listed above.
4. Add the variables, entering the Groq key only through Railway secrets.
5. Attach the `/data` volume before the first tester uses the service.
6. Generate a Railway staging domain and verify `GET /health` returns HTTP 200.
7. Exercise player search, demo squad, quota status, invalid preflight, and one
   successful Groq-backed recommendation.
8. Restart/redeploy the service and confirm the quota count persisted.
9. Configure the Cloudflare staging build with
   `NEXT_PUBLIC_API_BASE_URL=https://<railway-domain>` and test the browser flow.
10. Inspect Railway logs for secrets, stack traces, upstream errors and CORS
    failures before inviting testers.

Deployment and secret entry require explicit repository-owner confirmation.

## Smoke tests

Replace the hostname after Railway generates it:

```bash
curl --fail-with-body https://<railway-domain>/health
curl --fail-with-body "https://<railway-domain>/v1/players?position=MID&query=palmer"
```

The full conversational smoke test should be run through the Cloudflare staging
frontend so CORS and the anonymous browser quota are exercised together.

## Rollback

If staging fails, stop routing the Cloudflare preview build to the Railway API
and roll Railway back to the last healthy deployment. Preserve the `/data`
volume unless quota data is known to be corrupt. Never wipe or detach the volume
as a routine rollback step.

## Public-launch gate

Do not point the public Free experience at this API until issue #16 validates a
real finalized squad after the 2026/27 Gameweek 1 deadline. Only after that test
should `GAFFERTALK_ENVIRONMENT` become `production`, CORS be restricted to
`https://gaffertalk.com` (and any intentional canonical alias), and
`api.gaffertalk.com` be connected.
