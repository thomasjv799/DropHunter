# DropHunter - Phase 1 Plan & Retrospective

## The Initial Plan
The overarching goal for DropHunter Phase 1 was to establish a foundational MVP (Minimum Viable Product) for tracking video game prices and delivering alerts automatically. The bot needed to act as a personal gaming deal assistant, capable of interacting via a chat interface and passively scanning prices in the background.

**Core Objectives:**
1. **API Integration:** Connect securely to the IsThereAnyDeal (ITAD) V3 API to retrieve real game data and current best prices.
2. **Database Architecture:** Deploy a reliable remote database (Supabase/PostgreSQL) to maintain a stateful watchlist of games, price tracking history, and a log of past notifications.
3. **Conversational Chatbot Interface:** Build a conversational wrapper utilizing a large language model (LLM) through the Groq API (Llama-3), allowing users to type natural commands like "track Hades" or "list all the games," which the bot fulfills via autonomous tool-calling.
4. **Automated Price Checking Engine:** Construct a background daemon process (Cron job) to verify the tracked games against historical lows asynchronously and dispatch webhooks.
5. **Notification Delivery:** Hook up Discord to act as both the chat interface and the automated deal-alert endpoint.

---

## What We Achieved So Far 🚀

Phase 1 successfully implemented all initial planning goals, establishing a robust, modular, and functional Discord bot architecture:

### 1. Robust Groq AI Integration & Tool Execution
- Successfully mapped user text directly to actionable Python tools (`add_game`, `list_games`, `get_current_price`, `get_recent_deals`) using the Groq API.
- Implemented a dynamic "self-healing" fallback mechanism that actively catches and mathematically reconstructs malformed LLM tool hallucinations (e.g., Llama model XML tag glitches), preventing sudden bot crashes and improving usability.

### 2. IsThereAnyDeal (ITAD) Engine Formatting
- Natively bound the ITAD API queries to search specifically for the `'IN'` (India) region formats.
- Rewrote the engine to gather all prices across up to 10 storefronts dynamically, allowing the AI to effectively contrast standard prices across competitors (e.g., "Steam vs Epic Games") rather than just blinding returning one store.
- Validated text output explicitly enforces exact INR (₹) formatting cleanly across the Discord chat.

### 3. Automated Subsystem (Background Price Checker)
- Implemented `cron/price_check.py` to decouple checking from user interaction. The background script sequentially sweeps the DB for tracked games.
- Built a validation loop that calculates active pricing against historical logic (`price_history` database tables) to determine if a new, genuine deal exists, immediately deploying a styled webhook to Discord upon verification alongside AI-generated conversational commentary.

### 4. Supabase DB Infrastructure
- Created a reliable PostgreSQL `schema.sql` containing modularized elements (`games`, `price_history`, `notifications_log`).
- Set up automated `CASCADE` commands, indexing, and normalized timestamps, providing lightning-fast metrics matching for historical ITAD requests.

### Future Looking Ahead
With Phase 1 delivering a fast, working engine, the foundation has been firmly laid to integrate advanced LangGraph state machine logic, conversational memory summarization, and custom-defined threshold tracking for Phase 2.
