# Pro persistent workspace architecture

Status: accepted for Pro V1 Issue #47 on 2026-08-27.

## Decision

GafferTalk uses Supabase Auth and Supabase PostgreSQL for the account-bound Pro
workspace. Passwordless email OTP is the initial sign-in method. Development
starts on the Supabase Free plan; the production organization should move to
Pro before private beta so that the database does not pause and has automated
backups.

The Next.js application owns the browser session through `@supabase/ssr`
cookies. Its `/api/pro/workspace` route is a backend-for-frontend boundary: it
validates the Supabase session, forwards only the short-lived access token to
FastAPI, and never exposes a database credential to the browser. FastAPI
validates issuer, audience, expiry and signature against the project's JWKS.

FastAPI is the only application component that reads or writes workspace
tables. Every repository lookup and mutation begins with the authenticated
Supabase `sub` account ID. Browser-supplied account IDs are never accepted.
The public FPL Team ID connects a squad but is never authentication.

## Persisted model

- `accounts`: Supabase user ID and beta entitlement only. Email remains in Auth.
- `pro_workspaces`: one current workspace per account.
- `squad_state_versions`: immutable, normalized confirmed squads, current bank,
  free transfers, risk preference, captaincy state, source Gameweek and
  freshness. A compact public player snapshot makes the squad visible after a
  later login without retaining a raw manager payload.
- `conversations`: visible conversation metadata.
- `workspace_messages`: ordered user and assistant messages only.
- `decision_reports`: immutable grounded report JSON tied to the exact squad
  state version that produced it.

The current workspace points to its latest squad-state version. Reconfirmation
creates another version; it does not rewrite the evidence context of an older
report.

## Authorization and privacy boundaries

- FastAPI rejects missing, expired, wrongly issued or wrongly audienced bearer
  tokens before data access.
- Workspace queries join or filter through `account_id`; cross-account tests
  cover state, message and report reads and report mutations.
- Direct `anon` and `authenticated` table privileges are revoked in the
  migration. PostgreSQL RLS is enabled as a deny-by-default second boundary.
- The API database connection is server-only. Hosted deployments use the
  Supabase session pooler when the Railway network requires IPv4.
- Logs must contain request IDs, status, route and latency only. They must not
  contain raw conversations, access tokens, email addresses, raw FPL manager
  payloads or report JSON.
- Hidden chain-of-thought, raw Groq responses, credentials and temporary search
  candidates are not persisted.

## Trade-offs

Using one provider reduces integration and operational work versus separate
authentication and database vendors. It introduces Supabase coupling in the
session bootstrap and migrations. The application tables and authorization
repository remain ordinary PostgreSQL/SQLAlchemy, keeping the durable data
portable.

`@supabase/ssr` remains a provider-maintained beta package. Its version is
locked, session refresh runs through the Next.js 16 proxy, and sign-in plus
cross-session journeys are covered before dependency upgrades.

## Out of scope

This decision does not add billing, commercial subscription lifecycle or public
account deletion UI. Conditional plan persistence extends this workspace in
`docs/architecture/pro-conditional-plans.md`. Issue #49 owns commercial
entitlement enforcement; the wider account-control lifecycle is qualified before
private beta.
