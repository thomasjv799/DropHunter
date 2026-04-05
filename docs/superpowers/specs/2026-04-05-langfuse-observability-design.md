# DropHunter — Langfuse Observability Design

**Date:** 2026-04-05
**Scope:** Add end-to-end tracing and LLM observability to the LangGraph conversation pipeline using Langfuse cloud.

---

## Goals

- Trace every user message as a top-level Langfuse trace
- Capture child spans for each graph node (`load_memory`, `agent`, `execute_tools`, `save_memory`)
- Capture LLM generations with model name, input/output content, token usage, and latency
- Capture individual tool executions as child spans of `execute_tools`
- Capture Gemini summarization calls as generations within `save_memory`

---

## Trace Structure

```
Trace: run_graph (user_id, user_message)
├── Span: load_memory
├── Generation: agent → Groq (model, input, output, tokens, latency)
│   └── [if tool calls returned]
│       Span: execute_tools
│         ├── Span: tool:list_games → result
│         └── Span: tool:add_game → result
├── Generation: agent → Groq (follow-up, tools=[])
└── Span: save_memory
    └── [if summarization triggered]
        Generation: summarize → Gemini (model, input, output, tokens, latency)
```

---

## Approach

Use Langfuse Python SDK's `@observe()` decorator for automatic trace/span hierarchy. Manual `langfuse.generation()` calls inside `agent` and `save_memory` for LLM-specific metadata.

---

## Provider Changes

`AIProvider.chat_with_tools()` return format extended with optional `usage` field:

```python
# text response
{"text": "...", "usage": {"input_tokens": int, "output_tokens": int}}

# tool calls
{"tool_calls": [...], "usage": {"input_tokens": int, "output_tokens": int}}
```

- `GroqProvider` — reads from `response.usage.prompt_tokens` + `response.usage.completion_tokens`
- `GeminiProvider` — reads from `response.usage_metadata.prompt_token_count` + `response.usage_metadata.candidates_token_count`
- `_FallbackProvider` — passes `usage` through from whichever provider responded

---

## File Changes

| File | Change |
|------|--------|
| `requirements.txt` | Add `langfuse` |
| `ai/groq_provider.py` | Add `usage` dict to all return paths in `chat_with_tools` and `generate_text` |
| `ai/gemini_provider.py` | Add `usage` dict to all return paths in `chat_with_tools` and `generate_text` |
| `ai/graph.py` | Add `Langfuse()` client, `@observe()` on all nodes and `run_graph`, `langfuse.generation()` for LLM calls, child spans per tool |
| `.env` | Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` |

No changes to `bot/client.py`, `db/client.py`, or `bot/functions.py`.

---

## Environment Variables

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://us.cloud.langfuse.com
```

The Langfuse SDK reads these automatically when `Langfuse()` is instantiated.

---

## Error Handling

- If Langfuse is unreachable: SDK silently swallows errors — bot continues unaffected
- If `usage` is missing from provider response: `result.get("usage", {})` defaults to empty dict, generation is still recorded without token counts
- Tracing is best-effort and never blocks the conversation pipeline

---

## Testing

- Unit tests for `groq_provider.py` and `gemini_provider.py` verify `usage` is present in return dicts
- Graph node tests mock `langfuse` to verify `@observe()` calls don't break node behavior
- No integration test against live Langfuse (network dependency)
