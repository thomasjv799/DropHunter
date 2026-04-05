# Langfuse Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument the DropHunter LangGraph pipeline with Langfuse so every user conversation produces a trace with child spans for each graph node, LLM generations with token counts, and per-tool spans.

**Architecture:** Use Langfuse's `@observe()` decorator on `run_graph` and all four graph nodes to auto-build the trace hierarchy. Use `langfuse_context.update_current_observation()` inside `agent` to attach token usage. Wrap each tool dispatch in a `@observe()`-decorated helper so Langfuse records per-tool child spans. Add `@observe(as_type="generation")` to `GeminiProvider.generate_text` so summarization calls surface as child generations under `save_memory`.

**Tech Stack:** `langfuse` Python SDK (decorator API), Groq/Gemini providers, LangGraph, pytest-mock

---

## File Map

| File | Change |
|------|--------|
| `requirements.txt` | Add `langfuse` |
| `ai/groq_provider.py` | Add `usage` dict to every return path in `chat_with_tools` |
| `ai/gemini_provider.py` | Add `usage` dict to every return path in `chat_with_tools`; add `@observe(as_type="generation")` to `generate_text` |
| `ai/graph.py` | Add `@observe()` to all nodes and `run_graph`; update `agent` with `langfuse_context.update_current_observation()`; add `_run_tool()` helper with `@observe()` |
| `tests/test_providers.py` | New: unit tests verifying `usage` presence in provider responses |

No changes to `bot/client.py`, `db/client.py`, `bot/functions.py`, or `tests/test_graph.py` (existing graph tests continue to pass because Langfuse silently no-ops when credentials are absent).

---

### Task 1: Add langfuse to requirements and write failing provider usage tests

**Files:**
- Modify: `requirements.txt`
- Create: `tests/test_providers.py`

- [ ] **Step 1: Add langfuse to requirements.txt**

Open `requirements.txt` and add the line:

```
langfuse>=2.0.0
```

Final file should look like:

```
supabase==2.4.2
requests==2.31.0
discord.py==2.3.2
groq==0.11.0
google-generativeai==0.8.3
python-dotenv==1.0.1
tenacity==8.5.0
langgraph>=0.2.0
langfuse>=2.0.0
pytest==8.1.1
pytest-mock==3.14.0
```

- [ ] **Step 2: Install it**

```bash
pip install langfuse
```

Expected: installs without error.

- [ ] **Step 3: Write failing tests for GroqProvider usage**

Create `tests/test_providers.py`:

```python
# tests/test_providers.py
from unittest.mock import MagicMock


# ── GroqProvider ────────────────────────────────────────────────────────────

def _make_groq_response(content=None, tool_calls=None, prompt_tokens=10, completion_tokens=20):
    """Build a mock Groq chat completion response."""
    response = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    msg = response.choices[0].message
    msg.content = content
    msg.tool_calls = tool_calls
    return response


def _groq_provider(mocker, response):
    """Return a GroqProvider whose underlying client returns `response`."""
    mocker.patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = response
    mocker.patch("groq.Groq", return_value=mock_client)
    from ai.groq_provider import GroqProvider
    return GroqProvider()


def test_groq_chat_with_tools_text_response_has_usage(mocker):
    response = _make_groq_response(content="Hello!", tool_calls=None)
    provider = _groq_provider(mocker, response)
    result = provider.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}], tools=[]
    )
    assert "text" in result
    assert result["usage"] == {"input_tokens": 10, "output_tokens": 20}


def test_groq_chat_with_tools_tool_call_response_has_usage(mocker):
    mock_tc = MagicMock()
    mock_tc.function.name = "list_games"
    mock_tc.function.arguments = "{}"
    response = _make_groq_response(tool_calls=[mock_tc], prompt_tokens=15, completion_tokens=5)
    provider = _groq_provider(mocker, response)

    tools = [{"type": "function", "function": {"name": "list_games", "description": "...", "parameters": {}}}]
    result = provider.chat_with_tools(
        messages=[{"role": "user", "content": "list"}], tools=tools
    )
    assert "tool_calls" in result
    assert result["usage"] == {"input_tokens": 15, "output_tokens": 5}


# ── GeminiProvider ───────────────────────────────────────────────────────────

def _make_gemini_chat_response(text=None, tool_name=None, prompt_tokens=8, candidate_tokens=12):
    """Build a mock Gemini chat response."""
    response = MagicMock()
    response.usage_metadata.prompt_token_count = prompt_tokens
    response.usage_metadata.candidates_token_count = candidate_tokens
    if tool_name:
        part = MagicMock()
        part.function_call.name = tool_name
        part.function_call.args = {}
        response.parts = [part]
        response.text = None
    else:
        part = MagicMock()
        part.function_call.name = ""
        response.parts = [part]
        response.text = text or "Hi there"
    return response


def _gemini_provider(mocker, chat_response):
    """Return a GeminiProvider whose chat returns `chat_response`."""
    mocker.patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    mocker.patch("google.generativeai.configure")
    mock_chat = MagicMock()
    mock_chat.send_message.return_value = chat_response
    mock_model = MagicMock()
    mock_model.start_chat.return_value = mock_chat
    mocker.patch("google.generativeai.GenerativeModel", return_value=mock_model)
    from ai.gemini_provider import GeminiProvider
    return GeminiProvider()


def test_gemini_chat_with_tools_text_response_has_usage(mocker):
    response = _make_gemini_chat_response(text="Here's the list.", prompt_tokens=8, candidate_tokens=12)
    provider = _gemini_provider(mocker, response)
    result = provider.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}], tools=[]
    )
    assert "text" in result
    assert result["usage"] == {"input_tokens": 8, "output_tokens": 12}


def test_gemini_chat_with_tools_tool_call_response_has_usage(mocker):
    response = _make_gemini_chat_response(tool_name="list_games", prompt_tokens=5, candidate_tokens=3)
    provider = _gemini_provider(mocker, response)
    tools = [{"type": "function", "function": {"name": "list_games", "description": "...", "parameters": {}}}]
    result = provider.chat_with_tools(
        messages=[{"role": "user", "content": "list"}], tools=tools
    )
    assert "tool_calls" in result
    assert result["usage"] == {"input_tokens": 5, "output_tokens": 3}
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
pytest tests/test_providers.py -v
```

Expected: 4 tests FAIL with `KeyError: 'usage'` (providers don't return usage yet).

- [ ] **Step 5: Commit test file**

```bash
git add requirements.txt tests/test_providers.py
git commit -m "test: add failing provider usage tests; add langfuse to requirements"
```

---

### Task 2: Add usage to GroqProvider.chat_with_tools

**Files:**
- Modify: `ai/groq_provider.py`

- [ ] **Step 1: Update groq_provider.py**

Replace the entire `ai/groq_provider.py` with:

```python
import json
import os

from dotenv import load_dotenv

from ai.base import AIProvider

_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(AIProvider):
    def __init__(self):
        from groq import Groq

        load_dotenv()
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError("GROQ_API_KEY is not set. Add it to your .env file.")
        self._client = Groq(api_key=api_key)

    def generate_text(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        import re
        import groq

        try:
            response = self._client.chat.completions.create(
                model=_MODEL,
                messages=messages,
                tools=tools if tools else None,
            )
        except groq.BadRequestError as e:
            body = getattr(e, "body", {})
            err = body.get("error", {})
            if err.get("code") == "tool_use_failed" and "failed_generation" in err:
                failed_gen = err["failed_generation"]
                match = re.search(r"<function=([a-zA-Z0-9_]+)\s*(.*)", failed_gen)
                if match:
                    name = match.group(1)
                    args_str = match.group(2).strip()
                    if args_str.endswith("</function>"):
                        args_str = args_str[:-11].strip()
                    elif args_str.endswith(">"):
                        args_str = args_str[:-1].strip()

                    try:
                        args = json.loads(args_str) if args_str else {}
                        return {"tool_calls": [{"name": name, "arguments": args}], "usage": {}}
                    except json.JSONDecodeError:
                        pass
            raise

        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        message = response.choices[0].message
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Invalid JSON in tool call arguments: {tc.function.arguments!r}"
                    ) from e
                tool_calls.append(
                    {
                        "name": tc.function.name,
                        "arguments": arguments,
                    }
                )
            return {"tool_calls": tool_calls, "usage": usage}
        return {"text": message.content, "usage": usage}
```

- [ ] **Step 2: Run groq provider tests**

```bash
pytest tests/test_providers.py::test_groq_chat_with_tools_text_response_has_usage tests/test_providers.py::test_groq_chat_with_tools_tool_call_response_has_usage -v
```

Expected: both PASS.

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
pytest -v
```

Expected: all pre-existing tests pass, 2 Gemini usage tests still fail (not yet implemented).

- [ ] **Step 4: Commit**

```bash
git add ai/groq_provider.py
git commit -m "feat: add usage tokens to GroqProvider.chat_with_tools return"
```

---

### Task 3: Add usage to GeminiProvider.chat_with_tools and @observe to generate_text

**Files:**
- Modify: `ai/gemini_provider.py`

- [ ] **Step 1: Update gemini_provider.py**

Replace the entire `ai/gemini_provider.py` with:

```python
import os

import google.generativeai as genai
from dotenv import load_dotenv
from langfuse.decorators import langfuse_context, observe

from ai.base import AIProvider

_MODEL = "gemini-3-flash-preview"


def _to_gemini_tools(tools: list) -> list:
    """Convert OpenAI-style tool dicts to Gemini FunctionDeclaration list."""
    declarations = []
    for t in tools:
        fn = t.get("function", {})
        declarations.append(
            genai.types.FunctionDeclaration(
                name=fn.get("name", ""),
                description=fn.get("description", ""),
                parameters=fn.get("parameters", {}),
            )
        )
    return [genai.types.Tool(function_declarations=declarations)] if declarations else []


def _to_gemini_history(messages: list) -> list:
    """Convert OpenAI-style message list to Gemini chat history, skipping system messages."""
    history = []
    for m in messages[:-1]:  # last message sent via send_message
        if m["role"] == "system":
            continue
        role = "user" if m["role"] == "user" else "model"
        history.append({"role": role, "parts": [m["content"]]})
    return history


class GeminiProvider(AIProvider):
    def __init__(self):
        load_dotenv()
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set. Add it to your .env file.")
        genai.configure(api_key=api_key)
        self._model_name = _MODEL

    @observe(as_type="generation")
    def generate_text(self, prompt: str) -> str:
        model = genai.GenerativeModel(self._model_name)
        response = model.generate_content(prompt)
        langfuse_context.update_current_observation(
            model=self._model_name,
            input=prompt,
            output=response.text,
            usage={
                "input": response.usage_metadata.prompt_token_count,
                "output": response.usage_metadata.candidates_token_count,
            },
        )
        return response.text

    def chat_with_tools(self, messages: list, tools: list) -> dict:
        if not messages:
            raise ValueError("messages list cannot be empty")
        system_instruction = None
        if messages and messages[0]["role"] == "system":
            system_instruction = messages[0]["content"]

        gemini_tools = _to_gemini_tools(tools)
        model = genai.GenerativeModel(
            self._model_name,
            tools=gemini_tools or None,
            system_instruction=system_instruction,
        )
        history = _to_gemini_history(messages)
        chat = model.start_chat(history=history)
        response = chat.send_message(messages[-1]["content"])

        usage = {}
        if response.usage_metadata:
            usage = {
                "input_tokens": response.usage_metadata.prompt_token_count,
                "output_tokens": response.usage_metadata.candidates_token_count,
            }

        tool_calls = [
            {"name": part.function_call.name, "arguments": dict(part.function_call.args)}
            for part in response.parts
            if part.function_call.name
        ]
        if tool_calls:
            return {"tool_calls": tool_calls, "usage": usage}
        try:
            return {"text": response.text, "usage": usage}
        except ValueError as exc:
            raise ValueError(
                f"Gemini returned no usable text (response may be blocked): {exc}"
            ) from exc
```

- [ ] **Step 2: Run all provider tests**

```bash
pytest tests/test_providers.py -v
```

Expected: all 4 PASS.

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add ai/gemini_provider.py
git commit -m "feat: add usage tokens to GeminiProvider.chat_with_tools; @observe generate_text"
```

---

### Task 4: Instrument ai/graph.py with Langfuse @observe decorators

**Files:**
- Modify: `ai/graph.py`

- [ ] **Step 1: Replace ai/graph.py with the instrumented version**

```python
import logging
from typing import Literal, TypedDict

from langfuse.decorators import langfuse_context, observe
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


@observe()
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


@observe(as_type="generation")
def agent(state: GraphState) -> GraphState:
    provider = get_provider()
    # If tool results are already in messages, pass tools=[] to force a text response
    last_message = state["messages"][-1] if state["messages"] else {}
    has_tool_results = (
        last_message.get("role") == "user"
        and last_message.get("content", "").startswith("Tool results:")
    )
    tools = [] if has_tool_results else TOOLS
    result = provider.chat_with_tools(messages=state["messages"], tools=tools)

    usage = result.get("usage", {})
    if usage:
        langfuse_context.update_current_observation(
            usage={
                "input": usage.get("input_tokens"),
                "output": usage.get("output_tokens"),
            }
        )

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


@observe()
def _run_tool(name: str, arguments: dict) -> str:
    """Execute a single tool call and record it as a child Langfuse span."""
    langfuse_context.update_current_observation(name=f"tool:{name}", input=arguments)
    result = dispatch(name, arguments)
    langfuse_context.update_current_observation(output=result)
    return result


@observe()
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
            result = _run_tool(tc["name"], tc.get("arguments") or {})
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


@observe()
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


@observe()
def run_graph(user_id: str, user_message: str) -> str:
    langfuse_context.update_current_trace(user_id=user_id, input=user_message)
    initial_state: GraphState = {
        "user_id": user_id,
        "user_message": user_message,
        "messages": [{"role": "user", "content": user_message}],
        "tool_iteration": 0,
        "final_reply": "",
        "pending_tool_calls": [],
    }
    result = _get_graph().invoke(initial_state)
    langfuse_context.update_current_trace(output=result["final_reply"])
    return result["final_reply"]
```

- [ ] **Step 2: Run graph tests**

```bash
pytest tests/test_graph.py -v
```

Expected: all 14 tests PASS. The `@observe()` decorator is transparent when Langfuse credentials are absent — it silently no-ops.

Note: `test_execute_tools_dispatches_and_appends_results` and `test_execute_tools_handles_tool_error` both mock `ai.graph.dispatch`. The new `_run_tool()` helper calls the module-level `dispatch`, so the mocks still intercept it correctly.

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add ai/graph.py
git commit -m "feat: instrument LangGraph pipeline with Langfuse @observe and generation spans"
```

---

### Task 5: Verify end-to-end tracing in Langfuse cloud

This task is manual — no code changes.

- [ ] **Step 1: Confirm .env has the three Langfuse vars**

```bash
grep LANGFUSE .env
```

Expected output:
```
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=https://us.cloud.langfuse.com
```

- [ ] **Step 2: Start the bot and send a message**

```bash
python main.py
```

Send a Discord message: "list my tracked games"

- [ ] **Step 3: Check Langfuse dashboard**

Open [https://us.cloud.langfuse.com](https://us.cloud.langfuse.com) → Traces.

Verify the trace contains:
- Top-level trace `run_graph` with `user_id` and input/output
- Child span `load_memory`
- Child generation `agent` with token usage (input/output)
- Child span `execute_tools` → child span `tool:list_games`
- Child span `save_memory`

- [ ] **Step 4: Final commit if any tweaks were made**

```bash
git add -A
git commit -m "chore: verify Langfuse end-to-end trace"
```
