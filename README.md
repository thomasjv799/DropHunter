# DropHunter

This is a personal fun project so as to make my life easier when I buy games. The idea is to give the Bot some games to track and notify when the price is at the lowest. 
It will be a Python-powered AI assistant that helps gamers make smarter purchase decisions by tracking game prices and providing buy recommendations. It integrates the [IsThereAnyDeal API](https://isthereanydeal.com/) to fetch the latest game details, pricing history, and discounts. It also supports AI-driven real-time query handling via Groq function calling, and delivers notifications via Telegram or Discord bots.

---

## 🔧 Features

- 🏷️ Fetch historical and current game pricing using IsThereAnyDeal API
- 🤖 AI-based function calling with Groq for real-time game data
- 📈 Intelligent buy recommendations based on price history trends
- ⏰ Scheduled as a GitHub Actions cron job for daily or periodic checks
- 📲 Sends deal notifications and user-triggered queries via Telegram or Discord

---

## 🧠 Architecture Overview

- **Backend:** Python
- **Scheduler:** GitHub Actions (Cron)
- **APIs Used:**
  - [IsThereAnyDeal API](https://isthereanydeal.com/)
  - [Groq API](https://groq.com/)
- **Notifications:** Telegram Bot or Discord Webhook/Bot
- **AI Functions:** Function calling to get live pricing or recommendations

---

## 🚀 Status: Phase 1 Completed
DropHunter's core architecture is live. The bot actively handles Discord integrations, native LLM tool-calling (with self-healing fallback parsing), Supabase state tracking, and local automated cron-scheduling to verify the deepest INR (₹) game deals correctly.

---

## 🧠 Phase 2 Roadmap (In Progress)

We are actively overhauling the system to be a fully observable, stateful AI agent:
- **LangGraph Integration:** Transitioning from stateless loops to complex, manageable graph-based AI execution.
- **Conversational Memory:** Storing chat contexts in Supabase with summarized message histories so the bot remembers ongoing trains of thought.
- **Target Pricing:** Modifying the engine to notify you immediately if a game drops below a custom defined price threshold (e.g., `₹500`), rather than relying strictly on all-time historic lows.
- **Langfuse Observability:** Deep end-to-end tracing and monitoring for tool execution and LLM latency.

*(Detailed Phase 2 plans can be found in `docs/superpowers/plans/2026-04-05-drophunter-phase-2-roadmap.md`)*

---

## 🗂 Project Structure

├── bot/          # Discord bot integrations and tool functions
├── cron/         # Automated background scripts for price sweeps
├── ai/           # Groq LLM integration and fallback logic
├── db/           # Supabase connection schemas
├── docs/         # Architectural schemas and roadmap plans
├── tests/        # Pytest unit tests 
├── utils/        # ITAD API formatting and webhook utilities
├── main.py       # Main bot entrypoint
└── pyproject.toml
