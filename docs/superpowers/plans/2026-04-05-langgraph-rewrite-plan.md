# LangGraph Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stateless `on_message` dispatch loop with a LangGraph `StateGraph` that supports multi-step tool chaining and persistent per-user conversational memory stored in Supabase.

**Architecture:** A 4-node `StateGraph` (`load_memory → agent → execute_tools → save_memory`) wraps the existing `AIProvider` and `bot/functions.py` tools. Memory is persisted in two new Supabase tables (`chat_messages`, `chat_summary`). Gemini handles rolling summarization when message count exceeds 20.

**Tech Stack:** `langgraph>=0.2.0`, existing `groq`, `google-generativeai`, `supabase` Python clients.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `requirements.txt` | Modify | Add `langgraph` |
| `db/schema.sql` | Modify | Add `chat_messages`, `chat_summary` tables |
| `db/client.py` | Modify | Add `get_chat_context`, `save_turn`, `get_message_count`, `summarize_if_needed` |
| `ai/graph.py` | Create | `GraphState`, 4 nodes, routing, `run_graph()` entrypoint |
| `bot/client.py` | Modify | Replace dispatch loop with `run_graph()` call via `asyncio.to_thread` |
| `tests/test_db.py` | Modify | Tests for memory helpers |
| `tests/test_graph.py` | Create | Tests for all 4 graph nodes in isolation |

---

## Task 1: Add langgraph dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add langgraph to requirements.txt**

Open `requirements.txt` and add after `tenacity==8.5.0`:

```
langgraph>=0.2.0
```

- [ ] **Step 2: Install**

```bash
pip install -r requirements.txt
```

Expected: langgraph installs without errors.

- [ ] **Step 3: Verify import**

```bash
python -c "from langgraph.graph import StateGraph, END; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add langgraph dependency"
```

---

## Task 2: Add memory tables to schema

**Files:**
- Modify: `db/schema.sql`

- [ ] **Step 1: Add tables to schema.sql**

Append to the end of `db/schema.sql`:

```sql
create table if not exists chat_messages (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    role text not null,
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

- [ ] **Step 2: Run in Supabase SQL editor**

Copy and paste the above SQL into the Supabase SQL editor and execute. Verify both tables appear in the table list.

- [ ] **Step 3: Commit**

```bash
git add db/schema.sql
git commit -m "feat: add chat_messages and chat_summary tables to schema"
```

---

## Task 3: Add memory helpers to db/client.py

**Files:**
- Modify: `db/client.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Open `tests/test_db.py` and add:

```python
from unittest.mock import MagicMock, patch, call
from db.client import get_chat_context, save_turn, get_message_count, summarize_if_needed


def _make_client(summary_data=None, messages_data=None, count=0):
    """Helper: returns a mock Supabase client wired up for memory queries."""
    client = MagicMock()
    # chat_summary select chain
    summary_chain = MagicMock()
    summary_chain.execute.return_value.data = summary_data or []
    client.table("chat_summary").select.return_value.eq.return_value = summary_chain
    # chat_messages select chain
    msg_chain = MagicMock()
    msg_chain.execute.return_value.data = messages_data or []
    msg_chain.execute.return_value.count = count
    (client.table("chat_messages").select.return_value
     .eq.return_value.order.return_value.limit.return_value) = msg_chain
    return client


def test_get_chat_context_no_history(mocker):
    mock_client = _make_client()
    mocker.patch("db.client._get_client", return_value=mock_client)
    result = get_chat_context("user123")
    assert result == {"summary": None, "messages": []}


def test_get_chat_context_with_summary_and_messages(mocker):
    mock_client = _make_client(
        summary_data=[{"summary": "User tracks Hades."}],
        messages_data=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
    )
    mocker.patch("db.client._get_client", return_value=mock_client)
    result = get_chat_context("user123")
    assert result["summary"] == "User tracks Hades."
    assert len(result["messages"]) == 2


def test_get_chat_context_supabase_failure_returns_empty(mocker):
    mocker.patch("db.client._get_client", side_effect=Exception("connection refused"))
    result = get_chat_context("user123")
    assert result == {"summary": None, "messages": []}


def test_save_turn_inserts_two_messages(mocker):
    mock_client = MagicMock()
    mocker.patch("db.client._get_client", return_value=mock_client)
    save_turn("user123", "track hades", "Now tracking Hades.")
    mock_client.table("chat_messages").insert.assert_called_once_with([
        {"user_id": "user123", "role": "user", "content": "track hades"},
        {"user_id": "user123", "role": "assistant", "content": "Now tracking Hades."},
    ])


def test_get_message_count(mocker):
    mock_client = MagicMock()
    mock_client.table("chat_messages").select.return_value.eq.return_value.execute.return_value.count = 12
    mocker.patch("db.client._get_client", return_value=mock_client)
    assert get_message_count("user123") == 12


def test_summarize_if_needed_skips_when_under_threshold(mocker):
    mock_client = MagicMock()
    mock_client.table("chat_messages").select.return_value.eq.return_value.execute.return_value.count = 10
    mocker.patch("db.client._get_client", return_value=mock_client)
    mock_gemini = MagicMock()
    summarize_if_needed("user123", mock_gemini)
    mock_gemini.generate_text.assert_not_called()


def test_summarize_if_needed_triggers_and_deletes(mocker):
    mock_client = MagicMock()
    # count > 20
    mock_client.table("chat_messages").select.return_value.eq.return_value.execute.return_value.count = 21
    # oldest 15 messages
    oldest_msgs = [{"id": f"id{i}", "role": "user", "content": f"msg{i}"} for i in range(15)]
    (mock_client.table("chat_messages").select.return_value
     .eq.return_value.order.return_value.limit.return_value.execute.return_value.data) = oldest_msgs
    # no existing summary
    mock_client.table("chat_summary").select.return_value.eq.return_value.execute.return_value.data = []
    mocker.patch("db.client._get_client", return_value=mock_client)

    mock_gemini = MagicMock()
    mock_gemini.generate_text.return_value = "User tracks Hades with target ₹500."
    summarize_if_needed("user123", mock_gemini)

    mock_gemini.generate_text.assert_called_once()
    mock_client.table("chat_summary").upsert.assert_called_once()
    ids = [f"id{i}" for i in range(15)]
    mock_client.table("chat_messages").delete.return_value.in_.assert_called_once_with("id", ids)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db.py -k "chat_context or save_turn or message_count or summarize" -v
```

Expected: `ImportError` or `AttributeError` — functions don't exist yet.

- [ ] **Step 3: Implement memory helpers in db/client.py**

Add the following to the end of `db/client.py`:

```python
from datetime import datetime, timezone


def get_chat_context(user_id: str) -> dict:
    """Returns {'summary': str|None, 'messages': list[dict]} for a user. Never raises."""
    try:
        summary_result = (
            _get_client().table("chat_summary").select("summary").eq("user_id", user_id).execute()
        )
        summary = summary_result.data[0]["summary"] if summary_result.data else None

        messages_result = (
            _get_client()
            .table("chat_messages")
            .select("role,content")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        messages = list(reversed(messages_result.data))
        return {"summary": summary, "messages": messages}
    except Exception as exc:
        logger.warning("Failed to load chat context for %s: %s", user_id, exc)
        return {"summary": None, "messages": []}


def save_turn(user_id: str, user_message: str, assistant_message: str) -> None:
    _get_client().table("chat_messages").insert([
        {"user_id": user_id, "role": "user", "content": user_message},
        {"user_id": user_id, "role": "assistant", "content": assistant_message},
    ]).execute()


def get_message_count(user_id: str) -> int:
    result = (
        _get_client()
        .table("chat_messages")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    return result.count or 0


def summarize_if_needed(user_id: str, gemini_provider) -> None:
    """Summarize oldest 15 messages if total count exceeds 20. Never raises."""
    if get_message_count(user_id) <= 20:
        return

    oldest = (
        _get_client()
        .table("chat_messages")
        .select("id,role,content")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .limit(15)
        .execute()
    )
    if not oldest.data:
        return

    summary_result = (
        _get_client().table("chat_summary").select("summary").eq("user_id", user_id).execute()
    )
    existing_summary = summary_result.data[0]["summary"] if summary_result.data else "None"

    messages_text = "\n".join(f"{m['role']}: {m['content']}" for m in oldest.data)
    prompt = (
        "You are a memory manager for a Discord game deal assistant called DropHunter.\n"
        "Summarize the following conversation messages into a concise paragraph (max 150 words).\n"
        "Focus on: games the user is tracking, price targets they have set, deals they were notified about,\n"
        "and any preferences they have expressed. Merge with the existing summary if provided.\n\n"
        f"Existing summary: {existing_summary}\n\n"
        f"Messages to summarize:\n{messages_text}"
    )

    new_summary = gemini_provider.generate_text(prompt)

    _get_client().table("chat_summary").upsert(
        {
            "user_id": user_id,
            "summary": new_summary,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id",
    ).execute()

    ids_to_delete = [m["id"] for m in oldest.data]
    _get_client().table("chat_messages").delete().in_("id", ids_to_delete).execute()
    logger.info("Summarized %d messages for user %s", len(ids_to_delete), user_id)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db.py -k "chat_context or save_turn or message_count or summarize" -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add db/client.py tests/test_db.py
git commit -m "feat: add chat memory helpers to db/client"
```

---

## Task 4: Create ai/graph.py

**Files:**
- Create: `ai/graph.py`
- Create: `tests/test_graph.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_graph.py`:

```python
from unittest.mock import MagicMock, patch
from ai.graph import load_memory, agent, execute_tools, save_memory, route_after_agent, route_after_tools, GraphState


def _base_state(**overrides) -> GraphState:
    state: GraphState = {
        "user_id": "user123",
        "user_message": "track hades",
        "messages": [{"role": "user", "content": "track hades"}],
        "tool_iteration": 0,
        "final_reply": "",
        "pending_tool_calls": [],
    }
    state.update(overrides)
    return state


# --- load_memory ---

def test_load_memory_injects_system_prompt(mocker):
    mocker.patch("ai.graph.get_chat_context", return_value={"summary": None, "messages": []})
    result = load_memory(_base_state())
    assert result["messages"][0]["role"] == "system"
    assert "DropHunter" in result["messages"][0]["content"]


def test_load_memory_injects_summary_into_system(mocker):
    mocker.patch("ai.graph.get_chat_context", return_value={
        "summary": "User tracks Hades.",
        "messages": [],
    })
    result = load_memory(_base_state())
    assert "User tracks Hades." in result["messages"][0]["content"]


def test_load_memory_prepends_history_messages(mocker):
    mocker.patch("ai.graph.get_chat_context", return_value={
        "summary": None,
        "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
    })
    result = load_memory(_base_state())
    # system + 2 history + 1 current = 4
    assert len(result["messages"]) == 4


# --- agent ---

def test_agent_returns_final_reply_on_text(mocker):
    mock_provider = MagicMock()
    mock_provider.chat_with_tools.return_value = {"text": "Here is the price."}
    mocker.patch("ai.graph.get_provider", return_value=mock_provider)
    result = agent(_base_state())
    assert result["final_reply"] == "Here is the price."
    assert result["pending_tool_calls"] == []


def test_agent_returns_tool_calls(mocker):
    mock_provider = MagicMock()
    mock_provider.chat_with_tools.return_value = {
        "tool_calls": [{"name": "list_games", "arguments": {}}]
    }
    mocker.patch("ai.graph.get_provider", return_value=mock_provider)
    result = agent(_base_state())
    assert result["pending_tool_calls"] == [{"name": "list_games", "arguments": {}}]
    assert result["final_reply"] == ""


# --- execute_tools ---

def test_execute_tools_dispatches_and_appends_results(mocker):
    mocker.patch("ai.graph.dispatch", return_value="Game list: Hades")
    state = _base_state(pending_tool_calls=[{"name": "list_games", "arguments": {}}])
    result = execute_tools(state)
    assert result["tool_iteration"] == 1
    assert any("Game list: Hades" in m["content"] for m in result["messages"])


def test_execute_tools_stops_at_max_iterations(mocker):
    state = _base_state(tool_iteration=7, pending_tool_calls=[{"name": "list_games", "arguments": {}}])
    result = execute_tools(state)
    assert "wasn't able to complete" in result["final_reply"]


def test_execute_tools_handles_tool_error(mocker):
    mocker.patch("ai.graph.dispatch", side_effect=Exception("DB error"))
    state = _base_state(pending_tool_calls=[{"name": "list_games", "arguments": {}}])
    result = execute_tools(state)
    assert any("Error in list_games" in m["content"] for m in result["messages"])


# --- save_memory ---

def test_save_memory_calls_save_turn(mocker):
    mock_save = mocker.patch("ai.graph.save_turn")
    mocker.patch("ai.graph.GeminiProvider")
    mocker.patch("ai.graph.summarize_if_needed")
    state = _base_state(final_reply="Now tracking Hades.")
    save_memory(state)
    mock_save.assert_called_once_with("user123", "track hades", "Now tracking Hades.")


def test_save_memory_does_not_raise_on_failure(mocker):
    mocker.patch("ai.graph.save_turn", side_effect=Exception("supabase down"))
    state = _base_state(final_reply="ok")
    save_memory(state)  # should not raise


# --- routing ---

def test_route_after_agent_goes_to_tools_when_pending(mocker):
    state = _base_state(pending_tool_calls=[{"name": "list_games", "arguments": {}}], final_reply="")
    assert route_after_agent(state) == "execute_tools"


def test_route_after_agent_goes_to_save_when_reply(mocker):
    state = _base_state(final_reply="Here you go.", pending_tool_calls=[])
    assert route_after_agent(state) == "save_memory"


def test_route_after_tools_goes_to_agent_when_no_reply(mocker):
    state = _base_state(final_reply="", pending_tool_calls=[])
    assert route_after_tools(state) == "agent"


def test_route_after_tools_goes_to_save_when_reply(mocker):
    state = _base_state(final_reply="Done.", pending_tool_calls=[])
    assert route_after_tools(state) == "save_memory"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_graph.py -v
```

Expected: `ModuleNotFoundError: No module named 'ai.graph'`

- [ ] **Step 3: Create ai/graph.py**

Create `ai/graph.py`:

```python
import logging
from datetime import datetime, timezone
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from ai import get_provider
from ai.gemini_provider import GeminiProvider
from bot.functions import TOOLS, dispatch
from db.client import get_chat_context, save_turn, summarize_if_needed

logger = logging.getLogger("drophunter.graph")

MAX_TOOL_ITERATIONS = 7

_SYSTEM_PROMPT = (
    "You are DropHunter, a personal game deal assistant. "
    "When the user asks you to track, untrack, list games, check prices, see recent deals, "
    "check historical lows, or set target prices, use the available tools. "
    "You can call multiple tools in sequence if needed. "
    "For anything else, respond helpfully in plain text."
)


class GraphState(TypedDict):
    user_id: str
    user_message: str
    messages: list[dict]
    tool_iteration: int
    final_reply: str
    pending_tool_calls: list[dict]


def load_memory(state: GraphState) -> GraphState:
    context = get_chat_context(state["user_id"])

    system_content = _SYSTEM_PROMPT
    if context["summary"]:
        system_content += f"\n\nConversation history summary:\n{context['summary']}"

    history = [{"role": m["role"], "content": m["content"]} for m in context["messages"]]
    new_messages = (
        [{"role": "system", "content": system_content}]
        + history
        + [{"role": "user", "content": state["user_message"]}]
    )
    return {**state, "messages": new_messages}


def agent(state: GraphState) -> GraphState:
    provider = get_provider()
    result = provider.chat_with_tools(messages=state["messages"], tools=TOOLS)

    if "tool_calls" in result:
        return {
            **state,
            "pending_tool_calls": result["tool_calls"],
            "final_reply": "",
        }
    return {
        **state,
        "final_reply": result.get("text", "I'm not sure how to help with that."),
        "pending_tool_calls": [],
    }


def execute_tools(state: GraphState) -> GraphState:
    if state["tool_iteration"] >= MAX_TOOL_ITERATIONS:
        return {
            **state,
            "final_reply": "I wasn't able to complete that — please try again.",
            "pending_tool_calls": [],
        }

    tool_responses = []
    for tc in state["pending_tool_calls"]:
        try:
            result = dispatch(tc["name"], tc.get("arguments") or {})
            tool_responses.append(result)
        except Exception as exc:
            tool_responses.append(f"Error in {tc['name']}: {exc}")

    new_messages = state["messages"] + [
        {"role": "user", "content": f"Tool results: {'; '.join(tool_responses)}"}
    ]
    return {
        **state,
        "messages": new_messages,
        "tool_iteration": state["tool_iteration"] + 1,
        "pending_tool_calls": [],
    }


def save_memory(state: GraphState) -> GraphState:
    try:
        save_turn(state["user_id"], state["user_message"], state["final_reply"])
        summarize_if_needed(state["user_id"], GeminiProvider())
    except Exception as exc:
        logger.warning("Failed to save memory for %s: %s", state["user_id"], exc)
    return state


def route_after_agent(state: GraphState) -> Literal["execute_tools", "save_memory"]:
    if state.get("pending_tool_calls"):
        return "execute_tools"
    return "save_memory"


def route_after_tools(state: GraphState) -> Literal["agent", "save_memory"]:
    if state.get("final_reply"):
        return "save_memory"
    return "agent"


def _build_graph():
    g = StateGraph(GraphState)
    g.add_node("load_memory", load_memory)
    g.add_node("agent", agent)
    g.add_node("execute_tools", execute_tools)
    g.add_node("save_memory", save_memory)

    g.set_entry_point("load_memory")
    g.add_edge("load_memory", "agent")
    g.add_conditional_edges("agent", route_after_agent)
    g.add_conditional_edges("execute_tools", route_after_tools)
    g.add_edge("save_memory", END)

    return g.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def run_graph(user_id: str, user_message: str) -> str:
    initial_state: GraphState = {
        "user_id": user_id,
        "user_message": user_message,
        "messages": [{"role": "user", "content": user_message}],
        "tool_iteration": 0,
        "final_reply": "",
        "pending_tool_calls": [],
    }
    result = _get_graph().invoke(initial_state)
    return result["final_reply"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_graph.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/graph.py tests/test_graph.py
git commit -m "feat: add LangGraph StateGraph with 4-node conversation pipeline"
```

---

## Task 5: Update bot/client.py to use the graph

**Files:**
- Modify: `bot/client.py`

- [ ] **Step 1: Replace the dispatch loop**

Replace the entire content of `bot/client.py` with:

```python
import asyncio
import logging
import os
from typing import Optional

import discord
from dotenv import load_dotenv

from ai.graph import run_graph

logger = logging.getLogger("drophunter.bot")

_CHANNEL_ID: Optional[int] = None


def _get_channel_id() -> int:
    global _CHANNEL_ID
    if _CHANNEL_ID is None:
        load_dotenv()
        channel_id = os.environ.get("DISCORD_CHANNEL_ID")
        if not channel_id:
            raise EnvironmentError(
                "DISCORD_CHANNEL_ID is not set. Add it to your .env file."
            )
        _CHANNEL_ID = int(channel_id)
    return _CHANNEL_ID


intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    logger.info("DropHunter bot ready as %s", bot.user)
    logger.info("Listening on channel ID: %s", _get_channel_id())


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.channel.id != _get_channel_id():
        return

    user_id = str(message.author.id)
    user_text = message.content
    logger.info("Message from %s: %s", message.author, user_text[:100])

    try:
        async with message.channel.typing():
            reply = await asyncio.to_thread(run_graph, user_id, user_text)
    except Exception as exc:
        logger.error("Unhandled error processing message: %s", exc, exc_info=True)
        reply = (
            f"⚠️ Something went wrong while processing your request.\n"
            f"```\n{type(exc).__name__}: {exc}\n```"
        )

    await message.channel.send(reply[:2000])


def run():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.client").setLevel(logging.INFO)

    load_dotenv()
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise EnvironmentError(
            "DISCORD_BOT_TOKEN is not set. Add it to your .env file."
        )

    logger.info("Starting DropHunter bot...")
    bot.run(token, log_handler=None)
```

- [ ] **Step 2: Run full test suite to check nothing broke**

```bash
pytest -v
```

Expected: all existing tests still pass (bot/functions, itad, cron tests are unaffected).

- [ ] **Step 3: Smoke test locally with Docker**

```bash
docker build -t drophunter . && docker run --env-file .env drophunter
```

Expected log output:
```
INFO     drophunter.bot: Starting DropHunter bot...
INFO     drophunter.bot: DropHunter bot ready as DropHunter#2929
```

Send a message in Discord — verify the bot responds and logs show the graph nodes executing (`load_memory`, `agent`, etc.).

- [ ] **Step 4: Commit and push**

```bash
git add bot/client.py
git commit -m "feat: replace dispatch loop with LangGraph pipeline in bot/client"
git push origin main
```

---

## Task 6: Run the memory tables migration in Supabase

> This task is a manual step — no code changes.

- [ ] **Step 1: Open Supabase SQL editor**

Navigate to your Supabase project → SQL Editor.

- [ ] **Step 2: Run the migration**

```sql
create table if not exists chat_messages (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    role text not null,
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

- [ ] **Step 3: Verify**

In Supabase Table Editor, confirm `chat_messages` and `chat_summary` appear.

- [ ] **Step 4: Trigger a redeploy on Railway**

Push a trivial commit or manually trigger a redeploy so Railway picks up the new `langgraph` dependency and updated code.

```bash
git commit --allow-empty -m "chore: trigger redeploy for LangGraph migration"
git push origin main
```
