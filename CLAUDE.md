# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DropHunter is a Python-powered game price tracker. It monitors game prices via the [IsThereAnyDeal API](https://isthereanydeal.com/), uses [Groq](https://groq.com/) for AI-driven buy recommendations via function calling, runs on a GitHub Actions cron schedule, and sends notifications via Telegram or Discord.

## Planned Directory Structure

```
bot/        # Telegram/Discord bot integration
cron/       # GitHub Actions cron job scripts
ai/         # Groq function-calling setup
data/       # Game metadata, watchlists, logs
utils/      # API request helpers and data processing
main.py     # Entry point
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

- **Entry point:** `main.py` orchestrates the full pipeline: fetch prices → AI analysis → send notifications.
- **AI layer (`ai/`):** Uses Groq's function calling API to handle user queries and produce buy recommendations. Functions exposed to the LLM map to `utils/` helpers that call IsThereAnyDeal.
- **Bot layer (`bot/`):** Telegram bot or Discord webhook/bot listens for user-triggered queries and dispatches them to the AI layer.
- **Scheduler (`cron/`):** GitHub Actions workflow triggers periodic price checks. Secrets (API keys) are stored as GitHub Actions secrets and injected as environment variables.
- **Environment variables:** API keys for IsThereAnyDeal, Groq, Telegram, and Discord must be set (use `.env` locally; GitHub Actions secrets in CI).
