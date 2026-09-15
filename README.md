# DropHunter 

A private, multi-user Discord bot that tracks game and watch prices and alerts you when deals hit. You talk to it in plain English over DM; the owner permits who can use it, and every person's watchlist and alerts are isolated.
<img width="2442" height="1423" alt="image" src="https://github.com/user-attachments/assets/023ac522-b964-4e54-9fda-0fc24faded6f" />

---

## What it does

- **Track games** — tell the bot to watch a game and it monitors prices across all storefronts via [IsThereAnyDeal](https://isthereanydeal.com/)
- **Track watches** — paste a [Swiss Time House](https://www.swisstimehouse.com) product URL and set a target price; the bot fetches the listing (past Cloudflare via `cloudscraper`, parsing the page's `schema.org` Product JSON-LD) and alerts you when the price drops to/below your target
- **Custom price targets** — set a threshold (e.g. "alert me when Elden Ring drops below ₹500") instead of waiting for the all-time low
- **Scheduled price sweeps** — every 12 hours, scheduled jobs check each tracked game and watch and DM the owning user AI-written commentary when a deal is found
- **Multi-user & private** — DM-only; only the owner and users they permit (`/allow`) can use the bot. Each user's watchlist, history, and alerts are isolated by their Discord ID
- **Conversational memory** — the bot remembers your conversation across sessions using Postgres-backed chat history and rolling summarization (per user)
- **Multi-step reasoning** — powered by LangGraph, the bot can call multiple tools in sequence to answer complex questions

---

## Architecture

```
Discord DM (authorized users only — owner + allowlist)
      │  author.id → run_graph(user_id, …)
      ▼
 bot/client.py          auth gate, then asyncio.to_thread → run_graph()
      │
      ▼
 ai/graph.py            LangGraph StateGraph
  ├── load_memory       fetch this user's chat history + summary from configured Postgres
  ├── agent             Groq (Llama-3.3-70b) with tool calling, Gemini fallback
  ├── execute_tools     dispatch bot functions, injecting the caller's user_id
  └── save_memory       persist turn, rolling summarization via Gemini
      │
      ▼
 cron/price_check.py    scheduled sweep — every 12h via GitHub-hosted Actions (runner configurable)
      │  each row carries user_id
      ▼
 utils/discord.py       send_dm — per-user DM with Groq AI commentary

 cron/supabase_backup.py  every 3 days — upserts drophunter schema to Supabase (cold archive)
```

**AI layer:** `GroqProvider` (default) + `GeminiProvider` (optional fallback), or `OmniRouteProvider` with a configurable gateway and model. All implement `AIProvider`. Price alerts still send with plain commentary if AI is unavailable.

**Database:** PostgreSQL via psycopg2 — Supabase (`public` schema) during home-server maintenance, or local homelab Postgres (`drophunter` schema) — game tables (`games`, `price_history`, `notifications_log`), watch tables (`watches`, `watch_price_history`, `watch_notifications_log`), chat memory (`chat_messages`, `chat_summary`), and the access allowlist (`allowed_users`). `games`/`watches` carry a `user_id` owner column (composite-unique per user), so every query is scoped to the caller. The existing Supabase tables are the temporary cloud source. Home-server backups are disabled until explicitly re-enabled after reconciliation.

**Observability:** Full end-to-end tracing via [Langfuse](https://langfuse.com/) — every conversation produces a trace with child spans per graph node, LLM generations with token counts, and per-tool spans.

---

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

**Owner-only slash commands:** `/allow @user`, `/revoke @user`, `/listusers` (manage who may use the bot), plus `/clearmemory` and `/resetmemory` (per-user memory).

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

## Stack

| Layer | Tech |
|---|---|
| Bot | discord.py |
| AI | Groq (Llama-3.3-70b-versatile), Google Gemini (gemini-3-flash-preview) |
| Agent framework | LangGraph |
| Game prices | IsThereAnyDeal API v3 (IN region, INR) |
| Watch prices | Swiss Time House product pages (`cloudscraper` + BeautifulSoup, `schema.org` JSON-LD) |
| Database | Supabase (`public`) or homelab PostgreSQL (`drophunter`), psycopg2 |
| Backup | Optional home-server → Supabase archive; disabled during cloud operation |
| Observability | Langfuse v3 |
| Hosting | Scheduled games: GitHub cloud; conversational bot: persistent server |
| Scheduling | GitHub Actions — configurable runners, games default to cloud |
| Retry logic | tenacity (exponential backoff) |
| Tests | pytest + pytest-mock, real PostgreSQL in CI |

---

## Project structure

```
ai/                      AIProvider ABC, GroqProvider, GeminiProvider, LangGraph graph
bot/                     Discord client, tool function definitions
cron/
  price_check.py         Price sweep (--games / --watches) — runs via GitHub Actions every 12h
  supabase_backup.py     Cold backup — upserts drophunter schema to Supabase every 3 days
db/
  client.py              psycopg2 client (drophunter schema)
  migrations/
    001_drophunter_schema.sql  Schema DDL — run once on a fresh DB
  migrate_from_supabase.py     One-time migration script used during Phase 2 cutover
utils/                   ITAD API helpers, Swiss Time House watch fetcher, Discord webhook sender
tests/                   Pytest unit tests
main.py                  Entrypoint — starts bot + health check HTTP server
Dockerfile               Python 3.11-slim image
```

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
Use a trusted server database role; email and job-run tables have RLS and no public
API policies. A separate reporting role requires explicit `USAGE` on `ops` and
`SELECT` on `ops.job_runs`; the app's server role needs `INSERT` and `SELECT`.

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
cloud delivery. The inspection on 2026-09-15 found seven games and price history
through 2026-07-25; newer home-server changes may be absent.

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
needs the conversational bot to be running; during maintenance, the owner can
configure an existing user's `allowed_users.email` through the Supabase dashboard.
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
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
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
The bot's health endpoint is on port 8080. UI/SSO (#11) and percentage-based price
bounds (#8) remain separate follow-up work.
