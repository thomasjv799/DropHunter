# DropHunter - Phase 2 Roadmap & Phase 1 Retrospective

## Phase 1 Retrospective (Completed) 🚀
Phase 1 established the stable, core functional architecture for the DropHunter bot. 

**Key Accomplishments:**
- **Discord AI Agent:** Implemented a Discord bot acting as a fully conversational assistant using Groq API (Llama-3).
- **Tool Calling & Self-Healing:** Integrated native tool calling with a resilient fallback mechanism against LLM hallucinations to gracefully parse game tracking commands natively.
- **IsThereAnyDeal (ITAD) Engine:** Integrated the ITAD v3 API to locate actual cheapest store-front prices natively formatted in INR (₹).
- **Persistent Storage:** Integrated Supabase for persistent tracking of the `games` watchlist, `price_history`, and notification throttling.
- **Cron Infrastructure:** Established an automated background daemon (`price_check.py`) that periodically sweeps tracked games against all-time historical lows and dispatches Discord Webhook alerts accompanied by an AI-generated mini-analysis.

---

## Phase 2 Roadmap (LangGraph & AI Memory) 🧠📈
For Phase 2, the focus shifts structurally toward creating a much smarter, stateful, and observable AI Agent by utilizing LangGraph and Langfuse, while giving users granular control over their deals.

### 1. LangGraph Architecture Rewrite
The current bot runs a simple, stateless Python `dispatch()` while-loop. We will rewrite the conversational AI engine using **LangGraph**:
- Introduce robust graphs for routing user requests, thinking, and executing tasks iteratively.
- Streamline complex agentic loops (e.g., searching for games, confirming limits, parsing the output).
- Ensure safe transitions and easy extensibility for future tools.

### 2. Conversational Memory Persistence
Currently, every query is completely isolated (stateless). 
- Implement **Context Management**: The bot must recall what games the user *just* asked about.
- **Message Summarization**: Leverage the AI to automatically summarize the last 10 conversational turns and append the rolling summary state to Supabase.
- Store conversation threads natively in a new Supabase schema (`chat_memory`).

### 3. Custom Target Pricing Thresholds
- Enable users to define explicitly exactly how much they are willing to pay for a game (e.g., `"Track Hades but only notify me if it goes under ₹500"`).
- Decouple the hard reliance purely on "historical lows"—a notification will immediately fire if the target limit is bridged over any given store.
- Update tracking functions and Supabase schemas to cleanly support granular custom targets.

### 4. AI Observability (Langfuse Integration)
- Integrate **Langfuse** into the LangGraph pipelines.
- Trace every message, token usage, tool validation step, and generation latency.
- Achieve full observability to identify and systematically fix exact LLM hallucination paths or API slow-downs.

### 5. Comprehensive Unit Testing Expansion
- With the transition to LangGraph, we need rigorous mocks covering state management, graph transitions, and memory summarization.
- Add deep testing coverage in `tests/` matching new modular structure cleanly.

### 6. Dockerization & Deployment Architecture
- **Containerization**: Create a `Dockerfile` to cleanly package the DropHunter bot, LangGraph engine, and Python dependencies.
- **Docker Compose**: Introduce a `docker-compose.yml` file to handle environment orchestration cleanly, making it trivial to spin up the tracker locally.
- **Cloud Hosting 24/7**: Transition from local execution/GitHub Actions to deploying the container on a scalable cloud host (e.g., Railway, Render, or a dedicated VPS) to ensure the Discord bot and periodic sweeps remain alive around the clock natively.
