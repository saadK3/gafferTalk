# Pre-launch site operations

## Hosting

The GafferTalk landing page is prepared for Cloudflare Workers using the
official OpenNext adapter. The production Worker name is `gaffertalk-web` and
the canonical hostname is `gaffertalk.com`; `www.gaffertalk.com` should redirect
to the canonical hostname.

The deployment configuration lives in `apps/web/wrangler.jsonc`. Replace the
placeholder D1 database ID with the ID returned when the production
`gaffertalk-waitlist` database is created.

## Waitlist

Waitlist entries are stored in the D1 `waitlist_signups` table. The migration is
`apps/web/migrations/0001_waitlist.sql`. Email addresses are normalized to
lowercase, duplicate submissions are idempotent, and the form includes a hidden
bot trap plus Cloudflare Turnstile verification.

Production requires these runtime values:

- `NEXT_PUBLIC_TURNSTILE_SITE_KEY` as a build variable
- `TURNSTILE_SECRET_KEY` as an encrypted Worker secret

The form fails closed in production when the secret is missing. Never commit
either key to the repository.

## Deployment checklist

1. Run web lint, type checks, the Next.js build, and the Cloudflare build.
2. Apply the D1 migration before making the form public.
3. Configure Turnstile for `gaffertalk.com` and `www.gaffertalk.com`.
4. Set the build variable and Worker secret.
5. Deploy the Worker and add `gaffertalk.com` as its Custom Domain.
6. Configure `www.gaffertalk.com` to redirect permanently to the apex domain.
7. Submit a test address, verify one D1 row is created, then delete the test row.
8. Confirm HTTPS, metadata, the social preview, mobile layout, and the waitlist
   success/error states.
