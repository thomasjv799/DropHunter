# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DropHunter is a Python-powered Discord game and watch price tracker. It monitors game prices via the [IsThereAnyDeal API](https://isthereanydeal.com/) and watch prices from Swiss Time House product pages (fetched with `cloudscraper` to pass Cloudflare, parsed from `schema.org` Product JSON-LD), uses [Groq](https://groq.com/) (Llama-3) for AI-driven buy recommendations via function calling, persists state in Supabase (PostgreSQL), runs background price sweeps via a cron daemon, and delivers notifications via Discord.

**Phase 1 is complete.** Phase 2 targets LangGraph-based agentic rewrite, conversational memory, custom target pricing, and Langfuse observability. See `docs/superpowers/plans/2026-04-05-drophunter-phase-2-roadmap.md`.

## Directory Structure

```
ai/           # AIProvider ABC + Groq and Gemini provider implementations
bot/          # Discord bot client and tool function definitions
cron/         # Background price sweep daemon (price_check.py)
db/           # Supabase client and schema.sql (game + watch tables, chat memory)
docs/         # Architectural specs and roadmap plans
tests/        # Pytest unit tests
utils/        # ITAD API helpers, Swiss Time House watch fetcher (watches.py), Discord webhook utilities
main.py       # Discord bot entrypoint
pyproject.toml
```

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run main script
python main.py

# Run tests
pytest

# Run a single test
pytest tests/path/to/test_file.py::test_function_name

# Lint
ruff check .

# Format
ruff format .
```

## Architecture Notes

- **Entry point:** `main.py` starts the Discord bot, which listens for user messages and dispatches them to the AI layer.
- **AI layer (`ai/`):** `AIProvider` is an abstract base class. `groq_provider.py` implements Groq/Llama-3 tool calling with a self-healing fallback for malformed LLM responses. `gemini_provider.py` is an alternative provider.
- **Bot layer (`bot/`):** Discord bot client (`bot/client.py`) handles events. `bot/functions.py` defines the tools exposed to the LLM — game tools (`add_game`, `list_games`, `get_current_price`, `get_recent_deals`) and watch tools (`add_watch`, `list_watches`, `get_watch_price`, `set_watch_target`, `remove_watch`).
- **Database (`db/`):** Supabase/PostgreSQL via `db/client.py`. Game tables: `games` (watchlist), `price_history`, `notifications_log`. Watch tables: `watches`, `watch_price_history`, `watch_notifications_log`. Plus chat memory (`chat_messages`, `chat_summary`). See `db/schema.sql`.
- **Scheduler (`cron/`):** `cron/price_check.py` runs as a background daemon — `process_game` sweeps tracked games (compares against historical lows) and `process_watch` sweeps tracked watches (compares the lowest available price against the watch's required target). Both fire Discord webhook alerts with AI commentary. Also triggered via GitHub Actions.
- **Notifications (`utils/`):** `utils/discord.py` sends webhook messages (`send_deal_alert` for games, `send_watch_alert` for watches). `utils/itad.py` wraps the ITAD v3 API (`IN` region, INR). `utils/watches.py` fetches Swiss Time House product pages via `cloudscraper` (Cloudflare bypass) and parses the embedded `schema.org` Product JSON-LD into `{name, brand, reference, price}`.
- **Environment variables:** `ITAD_API_KEY`, `GROQ_API_KEY`, `DISCORD_TOKEN`, `DISCORD_WEBHOOK_URL`, `SUPABASE_URL`, `SUPABASE_KEY` — use `.env` locally; GitHub Actions secrets in CI.
