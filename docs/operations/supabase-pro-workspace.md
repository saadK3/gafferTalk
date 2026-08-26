# Supabase Pro workspace runbook

## Local setup

Prerequisites are the repository runtimes and a running Docker-compatible
engine. Install dependencies, start the local Supabase stack and copy the
printed public Auth values:

```text
pnpm install --frozen-lockfile
python3 -m pip install -e './apps/api[dev]'
make supabase-start
pnpm exec supabase status
```

Copy the root `.env.example` to `.env`. Copy the two
`NEXT_PUBLIC_SUPABASE_*` values into `apps/web/.env.local`, because Next.js is
started from `apps/web`. Keep the API-only database URL and Supabase URL in the
root `.env`.

The local stack applies `supabase/migrations/` and serves captured OTP email at
`http://127.0.0.1:54324`. The OTP template contains a six-digit code rather
than a magic link.

Start FastAPI and Next.js in separate terminals:

```text
make dev-api
make dev-web
```

Open `http://localhost:3000/pro/sign-in`, request a code, retrieve it from the
local email inbox, and complete the Team ID confirmation. `make supabase-reset`
replays the local schema from scratch and destroys local-only data.

## Automated verification

Backend tests use an isolated in-memory database and injected authenticated
accounts. They prove deterministic versioning and cross-account denial without
depending on a networked Auth service. The full local journey additionally
proves Supabase cookie refresh, email OTP, JWT verification and PostgreSQL
migrations.

## Hosted development checkpoint

Before Issue #47 is released to staging:

1. Create a separate Supabase development project in the region closest to the
   Railway API service.
2. Configure the OTP email template to include `{{ .Token }}` and add only the
   exact HTTPS GafferTalk redirect origins.
3. Apply committed migrations with `pnpm exec supabase db push` after reviewing
   `pnpm exec supabase db push --dry-run`.
4. Put the project URL and public publishable key in Cloudflare variables.
5. Put the Supabase URL and session-pooler database URL in Railway secrets.
6. Keep database passwords, secret/service keys and access tokens out of Git,
   chat, browser variables and logs.
7. Run sign-in, sign-out, cross-browser reopen, state versioning and named-report
   persistence smoke tests.

The built-in hosted email sender is for limited testing. Configure an approved
custom SMTP provider before inviting private-beta users. Upgrade the production
Supabase organization to Pro before that beta; no upgrade or deployment is
authorized by this runbook.

## Required variables

| Runtime | Variable | Secret |
| --- | --- | --- |
| Next.js | `NEXT_PUBLIC_SUPABASE_URL` | No |
| Next.js | `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | No |
| Next.js server | `GAFFERTALK_API_BASE_URL` | No |
| FastAPI | `GAFFERTALK_SUPABASE_URL` | No |
| FastAPI | `GAFFERTALK_SUPABASE_JWT_AUDIENCE` | No |
| FastAPI | `GAFFERTALK_DATABASE_URL` | Yes |

Never put a database URL or Supabase secret/service key in a `NEXT_PUBLIC_`
variable.
