# DropHunter — LangGraph Rewrite Design

**Date:** 2026-04-05
**Scope:** Replace the stateless `on_message` dispatch loop in `bot/client.py` with a LangGraph `StateGraph` that supports multi-step tool chaining and persistent conversational memory.

---

## Goals

- Enable the bot to chain multiple tool calls in a single turn (e.g. search game → check price → check historical low)
- Add persistent per-user conversational memory stored in Supabase
- Implement rolling summarization via Gemini to prevent context overflow
- Preserve existing `AIProvider` abstraction, self-healing fallback, and all bot tools

---

## Out of Scope

- Cron price check (`cron/price_check.py`) — stays independent and unchanged
- LangChain tool abstractions — we use our own `AIProvider` directly
- Multi-user isolation (single user for now)

---

## Graph Structure

```
[load_memory] → [agent] → [execute_tools] → [save_memory] → END
                  ↑              |
                  └──────────────┘ (loop if more tool calls, max 7 iterations)
```

### Nodes

**`load_memory`**
- Fetches `chat_summary.summary` (if exists) for this Discord user from Supabase
- Fetches the last 5 raw messages from `chat_messages`
- Injects both as context into the graph state before the agent runs
- On Supabase failure: logs a warning and proceeds without context — never blocks the turn

**`agent`**
- Calls the configured `AIProvider` (Groq + Gemini fallback) with full message context + tool definitions
- Returns either tool calls or a final text response
- Routes to `execute_tools` if tool calls are present, otherwise to `save_memory`

**`execute_tools`**
- Executes all tool calls from `bot/functions.py` dispatch
- Appends tool results back to state messages
- Increments iteration counter; if counter ≥ 7, exits with fallback message
- Routes back to `agent` for next reasoning step

**`save_memory`**
- Appends the user message and assistant response to `chat_messages` in Supabase
- If the user's message count exceeds 20, triggers rolling summarization:
  - Calls Gemini with a detailed summarization prompt
  - Merges new summary with existing `chat_summary` row (upsert)
  - Deletes the oldest 15 messages from `chat_messages`
- On summarization failure: keeps raw messages, retries next turn — never blocks the response

---

## Memory Schema

Two new tables added to `db/schema.sql`:

```sql
create table if not exists chat_messages (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    role text not null,        -- 'user' | 'assistant'
    content text not null,
    created_at timestamptz not null default now()
);

create table if not exists chat_summary (
    id uuid primary key default gen_random_uuid(),
    user_id text not null unique,
    summary text not null,
    updated_at timestamptz not null default now()
);

create index if not exists idx_chat_messages_user_id on chat_messages(user_id);
```

### Rolling Summary Logic

- Threshold: 20 messages triggers summarization
- Summarize oldest 15 messages via Gemini
- Merge with existing summary (upsert into `chat_summary`)
- Delete the 15 summarized messages from `chat_messages`
- Result: window stays at ≤ 5 recent raw messages + 1 rolling summary

### Summarization Prompt

```
You are a memory manager for a Discord game deal assistant called DropHunter.
Summarize the following conversation messages into a concise paragraph (max 150 words).
Focus on: games the user is tracking, price targets they have set, deals they were notified about,
and any preferences they have expressed. Merge with the existing summary if provided.

Existing summary: {existing_summary}

Messages to summarize:
{messages}
```

---

## File Changes

| File | Change |
|------|--------|
| `ai/graph.py` | **NEW** — StateGraph with 4 nodes, graph state TypedDict |
| `db/schema.sql` | Add `chat_messages` and `chat_summary` tables |
| `db/client.py` | Add memory helpers: `get_chat_context`, `save_turn`, `summarize_if_needed` |
| `bot/client.py` | Replace dispatch loop with `graph.invoke(state)` call |
| `bot/functions.py` | Unchanged |
| `ai/base.py` | Unchanged |
| `ai/groq_provider.py` | Unchanged |
| `ai/gemini_provider.py` | Unchanged |
| `ai/__init__.py` | Unchanged |

---

## Graph State

```python
class GraphState(TypedDict):
    user_id: str
    messages: list[dict]       # OpenAI-format message history for this turn
    tool_iteration: int        # counts tool call rounds, max 7
    final_reply: str           # populated when agent gives text response
```

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Supabase unreachable on load | Proceed without memory context, log warning |
| Summarization fails (Gemini error) | Keep raw messages, skip summarization, retry next turn |
| Tool execution error | Caught, returned as text to agent for natural response |
| Max iterations (7) reached | Exit graph, return fallback: "I wasn't able to complete that — please try again." |
| AI provider error | Existing `FallbackProvider` handles Groq → Gemini fallback transparently |

---

## Testing

- Unit test each graph node in isolation with mocked Supabase and AI provider
- Test rolling summarization trigger (>20 messages)
- Test max iteration guard (7 tool calls)
- Test memory load failure graceful degradation
- Existing `bot/functions.py` tests remain unchanged
