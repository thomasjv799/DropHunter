# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DropHunter is a Python-powered, multi-user Discord game and watch price tracker. It monitors game prices via the [IsThereAnyDeal API](https://isthereanydeal.com/) and watch prices from Swiss Time House product pages (fetched with `cloudscraper` to pass Cloudflare, parsed from `schema.org` Product JSON-LD), uses [Groq](https://groq.com/) (Llama-3) for AI-driven buy recommendations via function calling, persists state in Supabase (PostgreSQL), runs background price sweeps via a cron daemon, and delivers notifications via Discord. It is **DM-only and access-gated**: an owner (`OWNER_ID`) permits users via `/allow`, and each user's watchlist/history/alerts are isolated by their Discord `user_id`.

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
- **Bot layer (`bot/`):** Discord bot client (`bot/client.py`) handles events. It is **DM-only** and gates every message through `is_user_allowed(author.id)` (owner via `OWNER_ID`, or a row in `allowed_users`); owner-only slash commands `/allow`, `/revoke`, `/listusers` manage access. `bot/functions.py` defines the tools exposed to the LLM — game tools (`add_game`, `list_games`, `get_current_price`, `get_recent_deals`) and watch tools (`add_watch`, `list_watches`, `get_watch_price`, `set_watch_target`, `remove_watch`). Every tool takes `user_id` as its first argument; `dispatch(name, args, user_id)` injects the caller's id server-side (the LLM never supplies it).
- **Database (`db/`):** Supabase/PostgreSQL via `db/client.py`. Game tables: `games` (watchlist), `price_history`, `notifications_log`. Watch tables: `watches`, `watch_price_history`, `watch_notifications_log`. Chat memory (`chat_messages`, `chat_summary`) and the access allowlist (`allowed_users`). `games`/`watches` carry a `user_id` owner column (composite-unique per user: `(user_id, itad_id)`, `(user_id, swisstimehouse_url)`); all watchlist helpers are scoped by `user_id` (`get_games(user_id=None)`/`get_watches(None)` return all rows for the cron sweep). See `db/schema.sql`.
- **Scheduler (`cron/`):** `cron/price_check.py` runs the price sweep — `process_game` sweeps tracked games (compares against historical lows) and `process_watch` sweeps tracked watches (compares the lowest available price against the watch's required target). Both DM the owning user (`send_dm`) with AI commentary, skipping rows whose owner is no longer permitted. The entrypoint accepts `--games`/`--watches` flags (no flag = both). Sweeps run every 12h via two GitHub Actions workflows: `price_check.yml` (`--games`, GitHub-hosted runner) and `watch_check.yml` (`--watches`, **self-hosted runner on the Mac mini** — Swiss Time House's Cloudflare blocks GitHub's datacenter IPs, so the watch sweep must run from a residential IP).
- **Notifications (`utils/`):** `utils/discord.py` `send_dm(user_id, message)` DMs a user via the bot token + Discord REST (open DM channel → post). `utils/itad.py` wraps the ITAD v3 API (`IN` region, INR). `utils/watches.py` fetches Swiss Time House product pages via `cloudscraper` (Cloudflare bypass) and parses the embedded `schema.org` Product JSON-LD into `{name, brand, reference, price}`.
- **Environment variables:** `ITAD_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `AI_PROVIDER`, `DISCORD_BOT_TOKEN`, `OWNER_ID`, `SUPABASE_URL`, `SUPABASE_KEY`, `LANGFUSE_*` — use `.env` locally; GitHub Actions secrets in CI. (`DISCORD_CHANNEL_ID`/`DISCORD_WEBHOOK_URL` are no longer used — DM-only.)
