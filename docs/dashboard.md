# DropHunter dashboard

The web service is independent of the Discord bot. GitHub Actions continues checking prices while the web service handles interactive requests. It can run on a cloud container host or the home server; Actions itself cannot host an always-online dashboard.

## What works

- Google OAuth via Supabase, followed by explicit owner approval.
- Server-paginated game search, filters, sorting, targets, and additions (100-game web limit).
- Selected-game 7/30/90-day charts with exact timestamps/stores and visible observation gaps.
- Watch list, recent game alerts, notification email preferences, sign out.
- Separate in-memory demo with 100 sample games, requiring no credentials.

PS5 tracking remains issue #13. Watch additions still use the existing bot; this first web release lists watches. Web chat is not included. Charts show recorded best-store prices, not complete historical/all-time pricing. Prices older than 24 hours are marked stale. Summary “at target” counts use the last observation, which may be stale, and exclude historical-low trackers without explicit targets.

## Architecture

```text
Browser → Supabase Google OAuth (PKCE)
Browser → same-origin Flask API, Authorization: Bearer access-token
          → Supabase /auth/v1/user verifies identity
          → dashboard.accounts + existing Discord allowlist check
          → parameterized queries scoped to the approved Discord ID
GitHub Actions → existing Python tracker → same Postgres tables
```

Only the publishable Supabase key reaches the browser. Database, ITAD, and signing credentials stay on the server. DropHunter does not trust submitted Discord IDs, email matching, or user-editable metadata for authorization. Approval is checked for every API request; existing allowlist revocation also removes web access. Non-owner settings writes cannot recreate revoked permission rows.

The private `dashboard` schema is not exposed through Supabase's Data API. Keep direct browser table access disabled. The web service requires the trusted table-owner connection (as the existing tracker does); it enforces per-user access in every query. Use a dedicated limited server role with explicitly reviewed grants/policies if stricter database isolation is needed. Do not grant `anon` or `authenticated` blanket access. Other applications' tables in this project are untouched.

Each operation opens and closes its own connection; no shared bot connection is used. Connect via Supabase's session pooler. History queries use `(game_id,fetched_at,id)` indexes; only the requested game/time range is loaded, with a 1,000-observation ceiling. The UI's 100-game fixture is a functional check, not a production load benchmark. The 100-game addition limit is enforced by the web API; existing bot behavior is unchanged.

## Local development

Requires Python 3.11 and Node 22.

```sh
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements-web.lock
npm --prefix frontend ci
npm --prefix frontend run build
flask --app 'web.app:create_app()' run --port 8081
```

Open http://127.0.0.1:8081 and choose **Explore with sample data**. Demo edits remain in memory and disappear on reload. For frontend hot reload, also run `npm --prefix frontend run dev`; `/api` is proxied to port 8081.

## Server configuration

Set these in the deployment environment or an uncommitted `.env`:

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | TLS PostgreSQL connection; `LOCAL_DB_URL` is a legacy fallback |
| `DB_SCHEMA` | `public` for Supabase, `drophunter` for home-server tables |
| `SUPABASE_URL` | Project HTTPS URL |
| `SUPABASE_PUBLISHABLE_KEY` | `sb_publishable_...` key from Supabase API settings; never a secret/service-role key |
| `WEB_SECRET_KEY` | At least 32 random characters; signs expiring game selections, same value across workers |
| `OWNER_ID` | Existing owner Discord ID |
| `ITAD_API_KEY` | Game search key |

The web service does not need the Discord bot token or AI keys. It stores email preferences; the existing scheduler needs Resend credentials to deliver email. Generate the signing secret with `python -c 'import secrets; print(secrets.token_urlsafe(48))'` and save it privately.

## Apply the additive migration

Back up the database first. For existing cloud tracking, the earlier cloud-notifications migration must already be applied. Set the search path to the correct tracker schema:

```sh
PGOPTIONS='-c search_path=public' psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f supabase/migrations/20260926121657_dashboard_access.sql
```

For the home server substitute `search_path=drophunter`. Fresh databases also need the base schema and existing cloud-notifications migration described in the main README. This adds an empty approval table and indexes; it neither approves users nor alters tracked games.

## Google setup and first account

1. In Google Cloud, configure OAuth branding/audience and create a **Web application** OAuth client. Use the minimum `openid`, email, and profile scopes. If the app is in testing, add approved test users there too.
2. Set Google's authorized callback to `https://<project-ref>.supabase.co/auth/v1/callback`.
3. In Supabase **Authentication → Sign In / Providers → Google**, enable Google and save its client ID/secret. Keep these out of this repository and frontend.
4. Set the Supabase Site URL to the dashboard HTTPS origin. Add only exact needed callback destinations such as `https://dashboard.example.com/` (and localhost during development). Avoid wildcard production redirects.
5. Set the Google authorized JavaScript origin to the dashboard origin.
6. Sign in. The account remains pending with no data access. In Supabase **Authentication → Users**, independently verify the Google identity and copy its Supabase user UUID.
7. Verify which existing Discord user owns that watchlist. As the administrator, run:

```sh
python -m web.admin approve SUPABASE_USER_UUID --discord-id VERIFIED_DISCORD_ID --by OWNER_IDENTIFIER
```

Non-owner Discord IDs must also be on the existing `allowed_users` list. The CLI requires trusted database credentials; it is intentionally not a public endpoint. One Google account maps to one Discord account and each Discord account maps to at most one Google account. Do not accept identity claims from an unverified requester. To revoke:

```sh
python -m web.admin revoke SUPABASE_USER_UUID --by OWNER_IDENTIFIER
```

Users can click **Check approval again** after approval. Revocation blocks subsequent API requests, including previously issued access tokens. The mapping stores current approval metadata; it is not an immutable audit trail.

Reference: [Supabase Google setup](https://supabase.com/docs/guides/auth/social-login/auth-google).

## Production hosting

Build with `docker build -f Dockerfile.web -t drophunter-web .` and deploy behind an HTTPS reverse proxy on port 8080. The container runs as a non-root user with Gunicorn. Configure health checks against `/healthz`; this is process liveness, not database readiness. No cloud host or paid resources are created by the repository.

The API applies a basic per-process limit of 120 authenticated requests/minute/account. Put a shared rate limit at the reverse proxy for internet deployment, particularly before Supabase token verification and game-search calls. The process-local limiter is not a global abuse-prevention service. Search makes one bounded ITAD request; sweeps retain retry behavior. Tokens are kept by the Supabase browser client, so maintain the bundled-script CSP and do not add untrusted scripts. Configure Google as the only enabled sign-in method for dashboard users; approval remains required regardless of provider configuration.

## Checks and release

```sh
pip install -r requirements.txt -r requirements-dev.txt -r requirements-web.txt
python -m pytest -q
ruff check .
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Database tests require a **disposable** `TEST_DATABASE_URL`. Never point tests at production. CI creates PostgreSQL 17 and tests public and drophunter schemas. Browser tests run the built app with no live credentials and use sample data. Real Google consent/callback and production identity linking require a configured project and user-assisted sign-in; they cannot be proven by demo tests.

Rollback: redeploy the previous web image or stop the web service. Keep the additive approval table/indexes; the existing tracker does not depend on them. Revoke dashboard approvals if suspending web access. Do not roll back by deleting production game/history tables.
