# Tracker operations

[Back to the README](../README.md) · [Web dashboard setup](dashboard.md)

Run commands in this guide from the repository root. This guide covers the Discord bot, scheduled checks, database setup, notifications, and returning to the home server.

## Bot commands (natural language)

| What you say | What happens |
|---|---|
| "track Elden Ring" | adds to watchlist, alerts on historical low |
| "track Hades under ₹500" | adds with custom price target |
| "what games am I tracking?" | lists watchlist with targets |
| "remove Hollow Knight" | removes from watchlist |
| "what's the price of Hades?" | live prices across all stores |
| "what's the historical low for Celeste?" | all-time low from ITAD |
| "show recent deals" | last notified deals |
| "set target for Elden Ring to ₹800" | updates price threshold |
| "track this watch https://www.swisstimehouse.com/casio-g1714 under ₹30000" | adds a watch with a target price |
| "what watches am I tracking?" | lists tracked watches with targets |
| "what's the price of my Casio G1714?" | live price from Swiss Time House |
| "set watch target for Casio G1714 to ₹28000" | updates the watch threshold |
| "stop tracking the Casio G1714" | removes the watch |

**Owner-only commands:** `/allow @user`, `/revoke @user`, `/listusers`.

**Approved-user commands:** `/clearmemory` and `/resetmemory` manage your own conversation memory; `/setemail address` sets your notification email.

---

## Access & multi-user

The bot is **DM-only** and gated. The **owner** (`OWNER_ID` env var) is always allowed; everyone else must be permitted.

**Onboard a new user:**
1. Make sure you share a Discord server with them that the bot is also in (so the bot can DM them).
2. Run `/allow @them` (owner-only) — stores their Discord ID in `allowed_users`.
3. They DM the bot and use it normally; their data is isolated to them.
4. `/revoke @them` removes access; `/listusers` shows who's permitted.

Unauthorized DMs get a polite "not authorized" reply and are never processed (no data stored). Note: a user must allow DMs from the bot for deal-alert DMs to arrive.

---

## Cloud game tracking during maintenance

The game sweep can run without the conversational Discord bot. It sends DMs via
Discord's HTTP API using the bot token. Receiving conversational DMs still needs
an always-running server, so that part remains offline during maintenance.

### 1. Prepare the database

Use the existing Supabase tables with `DB_SCHEMA=public`. Do not run the home-server
base schema on top of them. Apply the additive migration once through the Supabase
SQL editor or a PostgreSQL client:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/20260915180826_cloud_notifications.sql
```

For a **fresh home-server database**, first apply
`db/migrations/001_drophunter_schema.sql`, then the migration above, and select
`DB_SCHEMA=drophunter`. For a fresh Supabase database, `db/schema.sql` is the base
schema; review its Data API grants and RLS before exposing it to clients.

`DATABASE_URL` takes precedence over `LOCAL_DB_URL`. Use the Supabase **session
pooler** connection string from the dashboard with `sslmode=require`; it supports
GitHub's IPv4 runners. See [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).
Use the trusted table-owner database role (Supabase `postgres`, or the home-server
table owner). Email and job-run tables have RLS and no public API policies. A
separate reporting role needs `USAGE` on `ops`, `SELECT` on `ops.job_runs`, and a
role-specific SELECT policy. A non-owner app role also needs explicit grants and
role-specific RLS policies; grants alone do not bypass RLS.

### 2. Configure GitHub Actions

In repository **Settings → Secrets and variables → Actions**, configure:

| Secrets | Purpose |
|---|---|
| `DATABASE_URL` | Supabase session-pooler PostgreSQL URL with TLS |
| `ITAD_API_KEY` | Game price lookup |
| `DISCORD_BOT_TOKEN`, `OWNER_ID` | Per-user Discord DMs and owner access |
| `GROQ_API_KEY` | Default AI commentary; alerts still work when AI is unavailable |
| `GEMINI_API_KEY` | Optional Gemini provider/fallback |
| `RESEND_API_KEY`, `EMAIL_FROM` | Optional per-user email alerts |
| `OMNIROUTE_API_KEY` | Required only when selecting OmniRoute |
| `LOCAL_DB_URL` | Optional legacy home-server connection; used only if `DATABASE_URL` is empty |

| Variables | Default | Purpose |
|---|---|---|
| `DB_SCHEMA` | `public` in Actions | `public` for Supabase, `drophunter` for home server |
| `GAME_RUNNER` | `ubuntu-latest` | Set `self-hosted` when moving checks back home |
| `GAME_CHECK_ENABLED` | enabled | `false` pauses scheduled games; manual checks still work |
| `WATCH_CHECK_ENABLED` | disabled | `true` enables watch runs, including manual runs |
| `WATCH_RUNNER` | `self-hosted` | Residential runner required by the watch source |
| `SUPABASE_BACKUP_ENABLED` | disabled | `true` enables home-server backups, including manual runs |
| `AI_PROVIDER` | existing secret or `groq` | `groq`, `gemini`, or `omniroute` |
| `OMNIROUTE_BASE_URL` | none | Gateway base URL including `/v1` |
| `OMNIROUTE_MODEL` | none | Model or combo configured in your gateway |
| `OMNIROUTE_TIMEOUT_SECONDS` | `60` | Request timeout, greater than 0 and at most 120 seconds |

Run **Actions → Game Price Check → Run workflow** with **check_only** enabled
first. This checks configuration and database access without sending alerts.
Then run normally. The game schedule is every 12 hours, at 00:00 and 12:00 UTC;
GitHub schedules can be delayed. Watch checks remain at :30 when enabled.

Each sweep writes one `ops.job_runs` row with start/end timestamps, `ok`/`error`,
error types and counts. `rows_swept` counts attempted items; `notifications_sent`
counts successfully completed Discord alert operations (email is optional and is
not included); `errors` counts item or fetch failures. Failed rows do not stop
other rows, but the workflow exits unsuccessfully. An inability to write the
operational record also fails the workflow.

### Data freshness and returning home

The Supabase archive is **upsert-only**: it can retain games or users previously
removed on the home server. Review its watchlist and allowed users before enabling
cloud delivery. Do not assume an archive reflects deletions or changes made on the home server after its last backup.

Keep backup jobs disabled while Supabase is primary. When maintenance ends:

1. Pause game schedules with `GAME_CHECK_ENABLED=false` and wait for any active run.
2. Reconcile cloud watchlists, permissions and notification history into the
   home-server database; do not overwrite newer cloud state with an old backup.
3. Apply the additive migration there. Set `GAME_RUNNER=self-hosted`,
   `DB_SCHEMA=drophunter`, and `DATABASE_URL` to the home-server connection (or
   remove it to use `LOCAL_DB_URL`).
4. Run the configuration check, then re-enable schedules. Enable watch and backup
   workflows only after confirming their database and runner are ready.

## Email alerts (#9)

Authorized users register their own email with `/setemail address`. The owner can
also use it without an existing allowlist row. Replies are private. The command
needs the conversational bot to be running; users can also update it in the authenticated web dashboard once deployed. During maintenance without web access, the owner can configure an existing user's `allowed_users.email` through Supabase.
Use each user's own address; there is no shared recipient fallback.

Resend requires a verified sender domain in `EMAIL_FROM`, for example
`DropHunter <alerts@example.com>`. Email follows the existing deal rules: the price
must meet the target/historical low and be lower than the last notified price.
Both game and watch alerts qualify. No address or no Resend settings means no
email. Email failures are logged without recipient details and do not interrupt
Discord delivery. Email failures are not retried independently once a Discord
notification is recorded. See the [Resend API](https://resend.com/docs/api-reference/emails/send-email).

## OmniRoute (#10)

```dotenv
AI_PROVIDER=omniroute
OMNIROUTE_BASE_URL=https://router.example.com/v1
OMNIROUTE_API_KEY=your-gateway-key
OMNIROUTE_MODEL=your-model-or-combo
OMNIROUTE_TIMEOUT_SECONDS=60
```

The provider supports text, tool calls and token usage through OmniRoute's
[chat completions API](https://github.com/diegosouzapw/OmniRoute/wiki/API-Reference).
The gateway must be reachable from the selected runner. A home-server gateway is
unavailable while that server is offline; use Groq directly until it returns.
Remote endpoints require HTTPS; loopback HTTP is allowed for development.
OmniRoute manages its own upstream routing; it is not wrapped in Gemini fallback.

## Running locally and testing

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-web.txt
cp .env.example .env
# Fill .env; local DB_SCHEMA defaults to drophunter.
.venv/bin/python main.py
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

CI runs tests against a disposable PostgreSQL 17 database, covering both existing
Supabase and home-server schemas. To run those integration tests locally, set
`TEST_DATABASE_URL` to a **disposable test database**; the tests create tables and
test data. Without it, only those integration tests are skipped.

The persistent bot can still run with the included Dockerfile:

```sh
docker build -t drophunter .
docker run -d --name drophunter --restart unless-stopped --env-file .env --network host drophunter
```

On the Linux home server, `--network host` lets the container reach local Postgres.
The bot's health endpoint is on port 8080. The web dashboard runs as a separate service; see [dashboard setup](dashboard.md). Percentage-based price bounds remain a separate follow-up (issue #8).
