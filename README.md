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
- **Conversational memory** — the bot remembers your conversation across sessions using Supabase-backed chat history and rolling summarization (per user)
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
  ├── load_memory       fetch this user's chat history + summary from Supabase
  ├── agent             Groq (Llama-3.3-70b) with tool calling, Gemini fallback
  ├── execute_tools     dispatch bot functions, injecting the caller's user_id
  └── save_memory       persist turn, rolling summarization via Gemini
      │
      ▼
 cron/price_check.py    scheduled sweep — games on GitHub-hosted Actions, watches on a self-hosted runner
      │  each row carries user_id
      ▼
 utils/discord.py       send_dm — per-user DM with Groq AI commentary
```

**AI layer:** `GroqProvider` (primary) + `GeminiProvider` (fallback). Both implement the `AIProvider` ABC. The `_FallbackProvider` wrapper auto-switches on failure.

**Database:** Supabase (PostgreSQL) — game tables (`games`, `price_history`, `notifications_log`), watch tables (`watches`, `watch_price_history`, `watch_notifications_log`), chat memory (`chat_messages`, `chat_summary`), and the access allowlist (`allowed_users`). `games`/`watches` carry a `user_id` owner column (composite-unique per user), so every query is scoped to the caller.

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
| Database | Supabase (PostgreSQL) |
| Observability | Langfuse v3 |
| Hosting | Self-hosted Mac mini (Ubuntu, Docker) on home LAN |
| Scheduling | GitHub Actions — game sweep (hosted runner) + watch sweep (self-hosted runner on the Mac mini) |
| Retry logic | tenacity (exponential backoff) |
| Tests | pytest + pytest-mock |

---

## Project structure

```
ai/           AIProvider ABC, GroqProvider, GeminiProvider, LangGraph graph
bot/          Discord client, tool function definitions
cron/         Price sweep (run via GitHub Actions; --games / --watches)
db/           Supabase client, schema.sql
utils/        ITAD API helpers, Swiss Time House watch fetcher, Discord webhook sender
tests/        Pytest unit tests
main.py       Entrypoint — starts bot + health check HTTP server
Dockerfile    Python 3.11-slim image
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
SUPABASE_URL=
SUPABASE_KEY=
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
docker run -d --name drophunter --restart unless-stopped --env-file .env -p 8080:8080 drophunter
```

Price sweeps run on a 12-hour schedule via **two GitHub Actions workflows**, split because Swiss Time House sits behind Cloudflare, which blocks GitHub's datacenter IP ranges:

- **Game Price Check** (`.github/workflows/price_check.yml`) — GitHub-hosted runner, runs `python -m cron.price_check --games` (ITAD works fine from datacenter IPs).
- **Watch Price Check** (`.github/workflows/watch_check.yml`) — **self-hosted runner on the Mac mini** (residential IP, so `cloudscraper` passes Cloudflare), runs `python -m cron.price_check --watches`.

Run a sweep manually with `python -m cron.price_check` (both), or pass `--games` / `--watches` for a single type.
