# DropHunter

A personal Discord bot that tracks game prices and alerts you when deals hit. Built as an AI agent — you talk to it in plain English and it handles the rest.

---

## What it does

- **Track games** — tell the bot to watch a game and it monitors prices across all storefronts via [IsThereAnyDeal](https://isthereanydeal.com/)
- **Custom price targets** — set a threshold (e.g. "alert me when Elden Ring drops below ₹500") instead of waiting for the all-time low
- **Daily price sweeps** — a background cron job checks every tracked game and fires a Discord webhook alert with AI commentary when a deal is found
- **Conversational memory** — the bot remembers your conversation across sessions using Supabase-backed chat history and rolling summarization
- **Multi-step reasoning** — powered by LangGraph, the bot can call multiple tools in sequence to answer complex questions

---

## Architecture

```
Discord message
      │
      ▼
 bot/client.py          asyncio.to_thread → run_graph()
      │
      ▼
 ai/graph.py            LangGraph StateGraph
  ├── load_memory       fetch chat history + summary from Supabase
  ├── agent             Groq (Llama-3.3-70b) with tool calling, Gemini fallback
  ├── execute_tools     dispatch bot functions (add/remove/list/price/deals)
  └── save_memory       persist turn, rolling summarization via Gemini
      │
      ▼
 cron/price_check.py    background daemon — sweeps all tracked games daily
      │
      ▼
 utils/discord.py       webhook alert with Groq AI commentary
```

**AI layer:** `GroqProvider` (primary) + `GeminiProvider` (fallback). Both implement the `AIProvider` ABC. The `_FallbackProvider` wrapper auto-switches on failure.

**Database:** Supabase (PostgreSQL) with four tables — `games`, `price_history`, `notifications_log`, `chat_messages`, `chat_summary`.

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

---

## Stack

| Layer | Tech |
|---|---|
| Bot | discord.py |
| AI | Groq (Llama-3.3-70b-versatile), Google Gemini (gemini-3-flash-preview) |
| Agent framework | LangGraph |
| Prices | IsThereAnyDeal API v3 (IN region, INR) |
| Database | Supabase (PostgreSQL) |
| Observability | Langfuse v3 |
| Hosting | Render (Web Service) |
| Retry logic | tenacity (exponential backoff) |
| Tests | pytest + pytest-mock |

---

## Project structure

```
ai/           AIProvider ABC, GroqProvider, GeminiProvider, LangGraph graph
bot/          Discord client, tool function definitions
cron/         Background price sweep daemon
db/           Supabase client, schema.sql
utils/        ITAD API helpers, Discord webhook sender
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
DISCORD_BOT_TOKEN=
DISCORD_WEBHOOK_URL=
DISCORD_CHANNEL_ID=
AI_PROVIDER=groq
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://us.cloud.langfuse.com
```

---

## Deployment

Runs on Render as a Web Service (free tier). The bot starts an HTTP server on port 8080 alongside Discord so Render's health checks pass.

The price sweep cron can be triggered via GitHub Actions on a schedule, or run locally with `python -m cron.price_check`.
