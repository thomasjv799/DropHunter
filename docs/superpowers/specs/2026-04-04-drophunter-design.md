# DropHunter — Design Spec

**Date:** 2026-04-04  
**Status:** Approved

---

## Overview

DropHunter is a personal game price tracker. It monitors a watchlist of games via the IsThereAnyDeal (ITAD) API, runs scheduled price checks every 12 hours via GitHub Actions, uses an AI provider (Groq or Gemini) to generate buy recommendations, and delivers alerts and interactive queries through Discord.

---

## Architecture

Two independent components share a single Supabase PostgreSQL database:

1. **Cron Worker** — stateless Python script triggered by GitHub Actions every 12h. Checks prices, detects deals, sends Discord webhook notifications.
2. **Discord Bot** — long-lived Python process hosted on Railway/Render free tier. Handles natural language commands from the user via function calling.

```
┌─────────────────────────────────────────────────────┐
│                   Supabase (DB)                     │
│  tables: games, price_history, notifications_log    │
└──────────────┬──────────────────────┬───────────────┘
               │                      │
       ┌───────▼────────┐    ┌────────▼──────────┐
       │ GitHub Actions  │    │   Discord Bot      │
       │  (cron, 12h)    │    │  (Railway/Render)  │
       │                 │    │                    │
       │ 1. Fetch prices │    │ Natural language    │
       │ 2. Compare hist │    │ commands via        │
       │ 3. AI analysis  │    │ Groq or Gemini      │
       │ 4. Webhook alert│    │                    │
       └───────┬─────────┘    └────────┬───────────┘
               │                       │
       ┌───────▼──────────────────────▼───────────┐
       │              Discord                       │
       │  #deals channel (webhook notifications)   │
       │  Bot commands (natural language)           │
       └───────────────────────────────────────────┘
```

---

## Data Model (Supabase)

### `games` — watchlist
| column | type | notes |
|---|---|---|
| id | uuid | PK |
| title | text | human-readable name |
| itad_id | text | ITAD's internal game ID |
| added_at | timestamp | |

### `price_history` — every price fetched by the cron job
| column | type | notes |
|---|---|---|
| id | uuid | PK |
| game_id | uuid | FK → games |
| price | numeric | current best price (USD) |
| regular_price | numeric | non-sale price |
| store | text | e.g. "Steam", "GOG" |
| fetched_at | timestamp | |

### `notifications_log` — deduplication of alerts
| column | type | notes |
|---|---|---|
| id | uuid | PK |
| game_id | uuid | FK → games |
| price | numeric | price that triggered the alert |
| notified_at | timestamp | |

---

## Cron Worker

**Entry point:** `cron/price_check.py`  
**Trigger:** GitHub Actions workflow (`.github/workflows/price_check.yml`), schedule configurable via cron expression (default: every 12h)

**Steps:**
1. Fetch all games from `games` table
2. Call ITAD API for each game's current best price across stores
3. Insert a row into `price_history`
4. Compare current price against historical low from `price_history`
5. If deal detected (current price ≤ historical low) AND no notification sent in last 12h → proceed
6. Call AI provider to generate a short buy recommendation sentence
7. POST to Discord webhook with price, store, discount %, and AI commentary
8. Insert into `notifications_log`

**Deal threshold:** current price is at or below the historical low recorded in `price_history`.

---

## Discord Bot

**Entry point:** `main.py`  
**Hosting:** Railway or Render free tier  
**Trigger:** Listens for messages in a configured Discord channel (`DISCORD_CHANNEL_ID`)

**Supported natural language intents:**
- "Track Elden Ring" → search ITAD, add to `games`
- "Stop tracking Hollow Knight" → remove from `games`
- "What games am I tracking?" → list `games`
- "What's the best price for Hades right now?" → live ITAD lookup
- "Show me recent deals" → query `notifications_log` + `games`

**Function calling tools exposed to the LLM:**
- `add_game(title)` — ITAD search + Supabase insert
- `remove_game(title)` — Supabase delete
- `list_games()` — Supabase select
- `get_current_price(title)` — live ITAD lookup
- `get_recent_deals()` — Supabase query

---

## AI Provider

**Abstraction:** `ai/base.py` defines an abstract interface. `ai/groq_provider.py` and `ai/gemini_provider.py` implement it.

**Selection:** controlled by env var `AI_PROVIDER=groq` or `AI_PROVIDER=gemini`. Swapping is a single config change with no code changes required.

Both providers are used for:
- Generating buy recommendation commentary in the cron worker
- Interpreting natural language and invoking function calls in the Discord bot

---

## Project Structure

```
DropHunter/
├── .github/
│   └── workflows/
│       └── price_check.yml      # Cron job, runs every 12h
├── bot/
│   ├── __init__.py
│   ├── client.py                # Discord bot setup and message listener
│   └── functions.py             # Function-calling tools (add_game, etc.)
├── ai/
│   ├── __init__.py
│   ├── base.py                  # Abstract AI provider interface
│   ├── groq_provider.py         # Groq implementation
│   └── gemini_provider.py       # Gemini implementation
├── cron/
│   ├── __init__.py
│   └── price_check.py           # Main cron worker script
├── db/
│   ├── __init__.py
│   └── client.py                # Supabase client + query helpers
├── utils/
│   ├── __init__.py
│   ├── itad.py                  # IsThereAnyDeal API wrapper
│   └── discord.py               # Webhook helper
├── main.py                      # Entry point for the Discord bot
├── requirements.txt
└── .env.example                 # Template for all required env vars
```

---

## Environment Variables

| variable | used by | notes |
|---|---|---|
| `SUPABASE_URL` | both | Supabase project URL |
| `SUPABASE_KEY` | both | Supabase anon/service key |
| `ITAD_API_KEY` | both | IsThereAnyDeal API key |
| `DISCORD_WEBHOOK_URL` | cron | For deal alert notifications |
| `DISCORD_BOT_TOKEN` | bot | For the interactive bot |
| `DISCORD_CHANNEL_ID` | bot | Channel the bot listens to |
| `GROQ_API_KEY` | both | Required if AI_PROVIDER=groq |
| `GEMINI_API_KEY` | both | Required if AI_PROVIDER=gemini |
| `AI_PROVIDER` | both | `groq` or `gemini` |

---

## Scope (Single User)

This is a personal single-user tool. No multi-tenancy, no authentication layer, no per-user watchlists. One Supabase project, one Discord server.
