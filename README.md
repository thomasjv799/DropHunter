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
  ├── load_memory       fetch this user's chat history + summary from local Postgres
  ├── agent             Groq (Llama-3.3-70b) with tool calling, Gemini fallback
  ├── execute_tools     dispatch bot functions, injecting the caller's user_id
  └── save_memory       persist turn, rolling summarization via Gemini
      │
      ▼
 cron/price_check.py    scheduled sweep — every 12h via self-hosted GitHub Actions runner
      │  each row carries user_id
      ▼
 utils/discord.py       send_dm — per-user DM with Groq AI commentary

 cron/supabase_backup.py  every 3 days — upserts drophunter schema to Supabase (cold archive)
```

**AI layer:** `GroqProvider` (primary) + `GeminiProvider` (fallback). Both implement the `AIProvider` ABC. The `_FallbackProvider` wrapper auto-switches on failure.

**Database:** Local homelab Postgres (`homelab` DB, `drophunter` schema) via psycopg2 — game tables (`games`, `price_history`, `notifications_log`), watch tables (`watches`, `watch_price_history`, `watch_notifications_log`), chat memory (`chat_messages`, `chat_summary`), and the access allowlist (`allowed_users`). `games`/`watches` carry a `user_id` owner column (composite-unique per user), so every query is scoped to the caller. Supabase is a cold backup only, synced every 3 days.

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
| Database | Local homelab Postgres (`drophunter` schema, psycopg2) |
| Backup | Supabase — cold archive, synced every 3 days |
| Observability | Langfuse v3 |
| Hosting | Self-hosted Mac mini (Ubuntu, Docker) on home LAN |
| Scheduling | GitHub Actions — all workflows on self-hosted runner |
| Retry logic | tenacity (exponential backoff) |
| Tests | pytest + pytest-mock |

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

## Running locally

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in env vars
cp .env.example .env

# Run the bot
python main.py

# Run tests
pytest

# Lint / format
ruff check .
ruff format .
```

**Required environment variables:**

```
LOCAL_DB_URL=               # postgresql://user:pass@localhost:5432/homelab
SUPABASE_URL=               # backup only
SUPABASE_KEY=               # backup only
ITAD_API_KEY=
GROQ_API_KEY=
GEMINI_API_KEY=
DISCORD_BOT_TOKEN=          # used by the bot and the cron (per-user DMs)
OWNER_ID=                   # your Discord user id — bootstrap admin + data owner
AI_PROVIDER=groq
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://us.cloud.langfuse.com
```

`DISCORD_CHANNEL_ID` and `DISCORD_WEBHOOK_URL` are no longer used (the bot is DM-only and alerts are sent as per-user DMs).

---

## Deployment

The bot runs on a **self-hosted Mac mini (Ubuntu)** as a Docker container, started from the included `Dockerfile`. It runs an HTTP health server on port 8080 alongside the Discord client.

```bash
docker build -t drophunter .
docker run -d --name drophunter --restart unless-stopped --env-file .env --network host drophunter
```

`--network host` is required so the container can reach local Postgres on port 5432.

### GitHub Actions workflows

All three workflows run on the **self-hosted runner** (needs local Postgres + residential IP for Cloudflare bypass):

| Workflow | Schedule | Command |
|---|---|---|
| Game Price Check | Every 12h at :00 | `python -m cron.price_check --games` |
| Watch Price Check | Every 12h at :30 | `python -m cron.price_check --watches` |
| Supabase Backup | Every 3 days at 03:00 | `python -m cron.supabase_backup` |

All support `workflow_dispatch` for manual runs from the GitHub Actions UI.

**GitHub secrets required:** `LOCAL_DB_URL`, `ITAD_API_KEY`, `DISCORD_WEBHOOK_URL`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `AI_PROVIDER`, `SUPABASE_URL`, `SUPABASE_KEY`

### Database setup (fresh install)

```bash
# Create schema and tables
docker exec homelab-postgres psql -U homelab -d homelab \
  -f db/migrations/001_drophunter_schema.sql
```
