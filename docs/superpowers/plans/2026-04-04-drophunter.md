# DropHunter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personal game price tracker that monitors a watchlist via IsThereAnyDeal, sends AI-enhanced deal alerts via Discord webhook on a 12h GitHub Actions schedule, and supports natural language watchlist management via a Discord bot.

**Architecture:** Two independent components (GitHub Actions cron worker + Discord bot) share a Supabase PostgreSQL database. The cron worker fetches prices, detects deals, and fires webhook alerts. The Discord bot runs on Railway/Render and handles natural language commands via Groq or Gemini function calling.

**Tech Stack:** Python 3.11+, supabase-py, requests, discord.py, groq, google-generativeai, python-dotenv, pytest, pytest-mock

---

## File Map

| File | Responsibility |
|---|---|
| `requirements.txt` | All Python dependencies |
| `.env.example` | Template for all required env vars |
| `db/client.py` | Supabase client + all query helpers |
| `utils/itad.py` | IsThereAnyDeal API wrapper |
| `utils/discord.py` | Discord webhook POST helper |
| `ai/base.py` | Abstract `AIProvider` interface |
| `ai/groq_provider.py` | Groq implementation |
| `ai/gemini_provider.py` | Gemini implementation |
| `ai/__init__.py` | `get_provider()` factory |
| `cron/price_check.py` | Cron worker orchestration |
| `.github/workflows/price_check.yml` | GitHub Actions schedule |
| `bot/functions.py` | Function-calling tools for LLM (add_game, etc.) |
| `bot/client.py` | Discord bot setup + message listener |
| `main.py` | Discord bot entry point |
| `tests/test_db.py` | DB client unit tests |
| `tests/test_itad.py` | ITAD wrapper unit tests |
| `tests/test_ai.py` | AI provider unit tests |
| `tests/test_cron.py` | Cron worker logic unit tests |
| `tests/test_bot_functions.py` | Bot function tools unit tests |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `db/__init__.py`, `utils/__init__.py`, `ai/__init__.py`, `cron/__init__.py`, `bot/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p db utils ai cron bot tests .github/workflows
touch db/__init__.py utils/__init__.py ai/__init__.py cron/__init__.py bot/__init__.py tests/__init__.py
```

- [ ] **Step 2: Create `requirements.txt`**

```
supabase==2.4.2
requests==2.31.0
discord.py==2.3.2
groq==0.11.0
google-generativeai==0.8.3
python-dotenv==1.0.1
pytest==8.1.1
pytest-mock==3.14.0
```

- [ ] **Step 3: Create `.env.example`**

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
ITAD_API_KEY=your-itad-api-key
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_BOT_TOKEN=your-discord-bot-token
DISCORD_CHANNEL_ID=123456789012345678
GROQ_API_KEY=your-groq-api-key
GEMINI_API_KEY=your-gemini-api-key
AI_PROVIDER=groq
```

- [ ] **Step 4: Create `tests/conftest.py`**

```python
import os
import pytest

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("ITAD_API_KEY", "test-itad-key")
os.environ.setdefault("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test")
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-bot-token")
os.environ.setdefault("DISCORD_CHANNEL_ID", "123456789")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AI_PROVIDER", "groq")
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example db/__init__.py utils/__init__.py ai/__init__.py cron/__init__.py bot/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: project scaffolding, dependencies, env template"
```

---

## Task 2: Supabase Schema

**Files:**
- No code files — SQL run in Supabase dashboard

- [ ] **Step 1: Open Supabase SQL editor**

Go to your Supabase project → SQL Editor → New query.

- [ ] **Step 2: Run schema migration**

```sql
create extension if not exists "pgcrypto";

create table if not exists games (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  itad_id text not null unique,
  added_at timestamptz not null default now()
);

create table if not exists price_history (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  price numeric not null,
  regular_price numeric not null,
  store text not null,
  fetched_at timestamptz not null default now()
);

create table if not exists notifications_log (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  price numeric not null,
  notified_at timestamptz not null default now()
);

create index if not exists idx_price_history_game_id on price_history(game_id);
create index if not exists idx_notifications_log_game_id on notifications_log(game_id);
```

- [ ] **Step 3: Verify tables created**

In Supabase → Table Editor, confirm `games`, `price_history`, and `notifications_log` all appear.

---

## Task 3: Supabase DB Client

**Files:**
- Create: `db/client.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db.py
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture
def mock_supabase(mocker):
    mock = MagicMock()
    mocker.patch("db.client.create_client", return_value=mock)
    return mock


def test_get_games_returns_list(mock_supabase):
    from db.client import get_games
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = [
        {"id": "abc", "title": "Elden Ring", "itad_id": "eldenring"}
    ]
    result = get_games()
    assert result == [{"id": "abc", "title": "Elden Ring", "itad_id": "eldenring"}]


def test_add_game_inserts_row(mock_supabase):
    from db.client import add_game
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "abc", "title": "Elden Ring", "itad_id": "eldenring"}
    ]
    result = add_game("Elden Ring", "eldenring")
    mock_supabase.table.return_value.insert.assert_called_once_with(
        {"title": "Elden Ring", "itad_id": "eldenring"}
    )
    assert result["title"] == "Elden Ring"


def test_remove_game_deletes_row(mock_supabase):
    from db.client import remove_game
    mock_supabase.table.return_value.delete.return_value.ilike.return_value.execute.return_value.data = [
        {"id": "abc"}
    ]
    result = remove_game("Elden Ring")
    assert result is True


def test_remove_game_returns_false_when_not_found(mock_supabase):
    from db.client import remove_game
    mock_supabase.table.return_value.delete.return_value.ilike.return_value.execute.return_value.data = []
    result = remove_game("Unknown Game")
    assert result is False


def test_insert_price_history(mock_supabase):
    from db.client import insert_price_history
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "xyz", "game_id": "abc", "price": 29.99}
    ]
    result = insert_price_history("abc", 29.99, 59.99, "Steam")
    mock_supabase.table.return_value.insert.assert_called_once_with(
        {"game_id": "abc", "price": 29.99, "regular_price": 59.99, "store": "Steam"}
    )
    assert result["price"] == 29.99


def test_get_historical_low_returns_min_price(mock_supabase):
    from db.client import get_historical_low
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"price": 14.99}
    ]
    result = get_historical_low("abc")
    assert result == 14.99


def test_get_historical_low_returns_none_when_no_history(mock_supabase):
    from db.client import get_historical_low
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    result = get_historical_low("abc")
    assert result is None


def test_was_recently_notified_true(mock_supabase):
    from db.client import was_recently_notified
    mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = [
        {"id": "n1"}
    ]
    assert was_recently_notified("abc") is True


def test_was_recently_notified_false(mock_supabase):
    from db.client import was_recently_notified
    mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
    assert was_recently_notified("abc") is False


def test_log_notification(mock_supabase):
    from db.client import log_notification
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "n1", "game_id": "abc", "price": 29.99}
    ]
    result = log_notification("abc", 29.99)
    assert result["game_id"] == "abc"


def test_get_recent_deals(mock_supabase):
    from db.client import get_recent_deals
    mock_supabase.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "n1", "price": 9.99, "games": {"title": "Hades"}}
    ]
    result = get_recent_deals()
    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'db.client'`

- [ ] **Step 3: Implement `db/client.py`**

```python
import os
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _client


def get_games() -> list[dict]:
    return _get_client().table("games").select("*").execute().data


def add_game(title: str, itad_id: str) -> dict:
    result = _get_client().table("games").insert({"title": title, "itad_id": itad_id}).execute()
    return result.data[0]


def remove_game(title: str) -> bool:
    result = _get_client().table("games").delete().ilike("title", title).execute()
    return len(result.data) > 0


def insert_price_history(game_id: str, price: float, regular_price: float, store: str) -> dict:
    result = _get_client().table("price_history").insert(
        {"game_id": game_id, "price": price, "regular_price": regular_price, "store": store}
    ).execute()
    return result.data[0]


def get_historical_low(game_id: str) -> float | None:
    result = (
        _get_client()
        .table("price_history")
        .select("price")
        .eq("game_id", game_id)
        .order("price", desc=False)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return float(result.data[0]["price"])


def was_recently_notified(game_id: str, hours: int = 12) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = (
        _get_client()
        .table("notifications_log")
        .select("id")
        .eq("game_id", game_id)
        .gte("notified_at", cutoff)
        .execute()
    )
    return len(result.data) > 0


def log_notification(game_id: str, price: float) -> dict:
    result = _get_client().table("notifications_log").insert(
        {"game_id": game_id, "price": price}
    ).execute()
    return result.data[0]


def get_recent_deals(limit: int = 5) -> list[dict]:
    return (
        _get_client()
        .table("notifications_log")
        .select("*, games(title)")
        .order("notified_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add db/client.py tests/test_db.py
git commit -m "feat: Supabase DB client with CRUD and query helpers"
```

---

## Task 4: ITAD API Wrapper

**Files:**
- Create: `utils/itad.py`
- Create: `tests/test_itad.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_itad.py
from unittest.mock import patch, MagicMock
import pytest


def test_search_game_returns_match():
    from utils.itad import search_game
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": "018d937f-1111-7000-aaaa-000000000001", "slug": "eldenring", "title": "ELDEN RING"}
    ]
    with patch("utils.itad.requests.get", return_value=mock_response):
        result = search_game("Elden Ring")
    assert result is not None
    assert result["id"] == "018d937f-1111-7000-aaaa-000000000001"
    assert result["title"] == "ELDEN RING"


def test_search_game_returns_none_when_empty():
    from utils.itad import search_game
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []
    with patch("utils.itad.requests.get", return_value=mock_response):
        result = search_game("Nonexistent Game XYZ")
    assert result is None


def test_get_best_price_returns_cheapest_deal():
    from utils.itad import get_best_price
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "id": "018d937f-1111-7000-aaaa-000000000001",
            "deals": [
                {
                    "shop": {"id": "steam", "name": "Steam"},
                    "price": {"amount": 29.99, "currency": "USD"},
                    "regular": {"amount": 59.99, "currency": "USD"},
                    "cut": 50,
                },
                {
                    "shop": {"id": "gog", "name": "GOG"},
                    "price": {"amount": 24.99, "currency": "USD"},
                    "regular": {"amount": 59.99, "currency": "USD"},
                    "cut": 58,
                },
            ],
        }
    ]
    with patch("utils.itad.requests.post", return_value=mock_response):
        result = get_best_price("018d937f-1111-7000-aaaa-000000000001")
    assert result is not None
    assert result["price"] == 24.99
    assert result["store"] == "GOG"
    assert result["regular_price"] == 59.99


def test_get_best_price_returns_none_when_no_deals():
    from utils.itad import get_best_price
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": "018d937f-1111-7000-aaaa-000000000001", "deals": []}
    ]
    with patch("utils.itad.requests.post", return_value=mock_response):
        result = get_best_price("018d937f-1111-7000-aaaa-000000000001")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_itad.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'utils.itad'`

- [ ] **Step 3: Implement `utils/itad.py`**

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

_BASE_URL = "https://api.isthereanydeal.com"


def _api_key() -> str:
    return os.environ["ITAD_API_KEY"]


def search_game(title: str) -> dict | None:
    """Search ITAD for a game by title. Returns the first match or None."""
    response = requests.get(
        f"{_BASE_URL}/games/search/v1",
        params={"title": title, "key": _api_key()},
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    return results[0]


def get_best_price(itad_id: str) -> dict | None:
    """
    Fetch current best price across all stores for a given ITAD game ID.
    Returns dict with keys: price, regular_price, store, cut — or None if no deals.
    """
    response = requests.post(
        f"{_BASE_URL}/games/prices/v3",
        params={"key": _api_key(), "country": "US"},
        json=[itad_id],
    )
    response.raise_for_status()
    data = response.json()
    if not data or not data[0].get("deals"):
        return None
    deals = data[0]["deals"]
    best = min(deals, key=lambda d: d["price"]["amount"])
    return {
        "price": best["price"]["amount"],
        "regular_price": best["regular"]["amount"],
        "store": best["shop"]["name"],
        "cut": best["cut"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_itad.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add utils/itad.py tests/test_itad.py
git commit -m "feat: IsThereAnyDeal API wrapper (search + best price)"
```

---

## Task 5: AI Provider Abstraction + Groq

**Files:**
- Create: `ai/base.py`
- Create: `ai/groq_provider.py`
- Create: `tests/test_ai.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ai.py
from unittest.mock import MagicMock, patch
import pytest


def test_groq_generate_text():
    from ai.groq_provider import GroqProvider
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="Great deal! Buy now."))
    ]
    with patch("ai.groq_provider.Groq", return_value=mock_client):
        provider = GroqProvider()
        result = provider.generate_text("Is this a good deal?")
    assert result == "Great deal! Buy now."


def test_groq_chat_with_tools_returns_tool_call():
    from ai.groq_provider import GroqProvider
    tool_call = MagicMock()
    tool_call.function.name = "add_game"
    tool_call.function.arguments = '{"title": "Elden Ring"}'
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=None,
                tool_calls=[tool_call],
            )
        )
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    with patch("ai.groq_provider.Groq", return_value=mock_client):
        provider = GroqProvider()
        result = provider.chat_with_tools(
            messages=[{"role": "user", "content": "Track Elden Ring"}],
            tools=[{"type": "function", "function": {"name": "add_game"}}],
        )
    assert result["tool_calls"] == [{"name": "add_game", "arguments": {"title": "Elden Ring"}}]


def test_groq_chat_with_tools_returns_text():
    from ai.groq_provider import GroqProvider
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="I can help with that.", tool_calls=None))
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    with patch("ai.groq_provider.Groq", return_value=mock_client):
        provider = GroqProvider()
        result = provider.chat_with_tools(
            messages=[{"role": "user", "content": "Hello"}],
            tools=[],
        )
    assert result["text"] == "I can help with that."
    assert "tool_calls" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ai.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `ai/base.py`**

```python
from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        """Generate a plain text response for a prompt."""

    @abstractmethod
    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        """
        Send messages with tool definitions. Returns either:
          {"text": "..."}                             — plain response
          {"tool_calls": [{"name": "...", "arguments": {...}}, ...]}  — tool invocation
        """
```

- [ ] **Step 4: Implement `ai/groq_provider.py`**

```python
import json
import os
from groq import Groq
from ai.base import AIProvider
from dotenv import load_dotenv

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(AIProvider):
    def __init__(self):
        self._client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def generate_text(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=tools if tools else None,
        )
        message = response.choices[0].message
        if message.tool_calls:
            return {
                "tool_calls": [
                    {
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                    for tc in message.tool_calls
                ]
            }
        return {"text": message.content}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_ai.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add ai/base.py ai/groq_provider.py tests/test_ai.py
git commit -m "feat: AI provider abstraction and Groq implementation"
```

---

## Task 6: Gemini AI Provider

**Files:**
- Modify: `tests/test_ai.py`
- Create: `ai/gemini_provider.py`

- [ ] **Step 1: Add failing Gemini tests to `tests/test_ai.py`**

Append to the existing file:

```python
def test_gemini_generate_text():
    from ai.gemini_provider import GeminiProvider
    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = "Solid deal, pick it up."
    mock_genai = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model
    with patch("ai.gemini_provider.genai", mock_genai):
        provider = GeminiProvider()
        result = provider.generate_text("Is this worth buying?")
    assert result == "Solid deal, pick it up."


def test_gemini_chat_with_tools_returns_tool_call():
    from ai.gemini_provider import GeminiProvider
    mock_part = MagicMock()
    mock_part.function_call.name = "list_games"
    mock_part.function_call.args = {}
    mock_part.text = None

    mock_response = MagicMock()
    mock_response.parts = [mock_part]

    mock_chat = MagicMock()
    mock_chat.send_message.return_value = mock_response

    mock_model = MagicMock()
    mock_model.start_chat.return_value = mock_chat

    mock_genai = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model

    with patch("ai.gemini_provider.genai", mock_genai):
        provider = GeminiProvider()
        result = provider.chat_with_tools(
            messages=[{"role": "user", "content": "What am I tracking?"}],
            tools=[{"type": "function", "function": {"name": "list_games"}}],
        )
    assert result["tool_calls"] == [{"name": "list_games", "arguments": {}}]
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
pytest tests/test_ai.py::test_gemini_generate_text tests/test_ai.py::test_gemini_chat_with_tools_returns_tool_call -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `ai/gemini_provider.py`**

```python
import os
import google.generativeai as genai
from ai.base import AIProvider
from dotenv import load_dotenv

load_dotenv()

_MODEL = "gemini-1.5-flash"


def _to_gemini_tools(tools: list[dict]) -> list:
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


def _to_gemini_history(messages: list[dict]) -> list:
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
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        self._model_name = _MODEL

    def generate_text(self, prompt: str) -> str:
        model = genai.GenerativeModel(self._model_name)
        response = model.generate_content(prompt)
        return response.text

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        # Extract system message and pass as system_instruction (Gemini doesn't use "system" role)
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

        for part in response.parts:
            if part.function_call.name:
                return {
                    "tool_calls": [
                        {"name": part.function_call.name, "arguments": dict(part.function_call.args)}
                    ]
                }
        return {"text": response.text}
```

- [ ] **Step 4: Implement `ai/__init__.py` provider factory**

```python
import os
from ai.base import AIProvider


def get_provider() -> AIProvider:
    provider = os.environ.get("AI_PROVIDER", "groq").lower()
    if provider == "groq":
        from ai.groq_provider import GroqProvider
        return GroqProvider()
    if provider == "gemini":
        from ai.gemini_provider import GeminiProvider
        return GeminiProvider()
    raise ValueError(f"Unknown AI_PROVIDER: {provider!r}. Must be 'groq' or 'gemini'.")
```

- [ ] **Step 5: Run all AI tests**

```bash
pytest tests/test_ai.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add ai/gemini_provider.py ai/__init__.py tests/test_ai.py
git commit -m "feat: Gemini AI provider and get_provider() factory"
```

---

## Task 7: Discord Webhook Helper

**Files:**
- Create: `utils/discord.py`
- Create: `tests/test_discord_webhook.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_discord_webhook.py
from unittest.mock import patch, MagicMock


def test_send_deal_alert_posts_to_webhook():
    from utils.discord import send_deal_alert
    mock_response = MagicMock()
    mock_response.status_code = 204
    with patch("utils.discord.requests.post", return_value=mock_response) as mock_post:
        send_deal_alert(
            game_title="Elden Ring",
            price=29.99,
            regular_price=59.99,
            store="Steam",
            cut=50,
            ai_commentary="Lowest price in 2 years.",
        )
    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert "Elden Ring" in payload["content"]
    assert "29.99" in payload["content"]
    assert "Steam" in payload["content"]
    assert "Lowest price in 2 years." in payload["content"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_discord_webhook.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `utils/discord.py`**

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()


def send_deal_alert(
    game_title: str,
    price: float,
    regular_price: float,
    store: str,
    cut: int,
    ai_commentary: str,
) -> None:
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    message = (
        f"**Deal Alert: {game_title}**\n"
        f"${price:.2f} on {store} ({cut}% off, was ${regular_price:.2f})\n"
        f"{ai_commentary}"
    )
    response = requests.post(webhook_url, json={"content": message})
    response.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_discord_webhook.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add utils/discord.py tests/test_discord_webhook.py
git commit -m "feat: Discord webhook helper for deal alerts"
```

---

## Task 8: Cron Worker

**Files:**
- Create: `cron/price_check.py`
- Create: `tests/test_cron.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cron.py
from unittest.mock import patch, MagicMock, call
import pytest


@pytest.fixture
def sample_game():
    return {"id": "game-uuid-1", "title": "Elden Ring", "itad_id": "018d937f-aaaa"}


def test_process_game_sends_alert_when_deal_detected(sample_game, mocker):
    from cron.price_check import process_game

    mocker.patch("cron.price_check.get_best_price", return_value={
        "price": 14.99, "regular_price": 59.99, "store": "Steam", "cut": 75
    })
    mocker.patch("cron.price_check.insert_price_history", return_value={})
    mocker.patch("cron.price_check.get_historical_low", return_value=14.99)
    mocker.patch("cron.price_check.was_recently_notified", return_value=False)
    mock_provider = MagicMock()
    mock_provider.generate_text.return_value = "Best price ever!"
    mocker.patch("cron.price_check.get_provider", return_value=mock_provider)
    mock_alert = mocker.patch("cron.price_check.send_deal_alert")
    mock_log = mocker.patch("cron.price_check.log_notification")

    process_game(sample_game)

    mock_alert.assert_called_once_with(
        game_title="Elden Ring",
        price=14.99,
        regular_price=59.99,
        store="Steam",
        cut=75,
        ai_commentary="Best price ever!",
    )
    mock_log.assert_called_once_with("game-uuid-1", 14.99)


def test_process_game_skips_when_not_a_deal(sample_game, mocker):
    from cron.price_check import process_game

    mocker.patch("cron.price_check.get_best_price", return_value={
        "price": 50.00, "regular_price": 59.99, "store": "Steam", "cut": 17
    })
    mocker.patch("cron.price_check.insert_price_history", return_value={})
    mocker.patch("cron.price_check.get_historical_low", return_value=14.99)
    mocker.patch("cron.price_check.was_recently_notified", return_value=False)
    mock_alert = mocker.patch("cron.price_check.send_deal_alert")

    process_game(sample_game)

    mock_alert.assert_not_called()


def test_process_game_skips_when_recently_notified(sample_game, mocker):
    from cron.price_check import process_game

    mocker.patch("cron.price_check.get_best_price", return_value={
        "price": 14.99, "regular_price": 59.99, "store": "Steam", "cut": 75
    })
    mocker.patch("cron.price_check.insert_price_history", return_value={})
    mocker.patch("cron.price_check.get_historical_low", return_value=14.99)
    mocker.patch("cron.price_check.was_recently_notified", return_value=True)
    mock_alert = mocker.patch("cron.price_check.send_deal_alert")

    process_game(sample_game)

    mock_alert.assert_not_called()


def test_process_game_skips_when_no_price_data(sample_game, mocker):
    from cron.price_check import process_game

    mocker.patch("cron.price_check.get_best_price", return_value=None)
    mock_insert = mocker.patch("cron.price_check.insert_price_history")

    process_game(sample_game)

    mock_insert.assert_not_called()


def test_run_checks_all_games(mocker):
    from cron.price_check import run

    mocker.patch("cron.price_check.get_games", return_value=[
        {"id": "1", "title": "Game A", "itad_id": "aaa"},
        {"id": "2", "title": "Game B", "itad_id": "bbb"},
    ])
    mock_process = mocker.patch("cron.price_check.process_game")

    run()

    assert mock_process.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cron.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `cron/price_check.py`**

```python
from db.client import (
    get_games,
    insert_price_history,
    get_historical_low,
    was_recently_notified,
    log_notification,
)
from utils.itad import get_best_price
from utils.discord import send_deal_alert
from ai import get_provider


def process_game(game: dict) -> None:
    price_data = get_best_price(game["itad_id"])
    if price_data is None:
        print(f"[{game['title']}] No price data available, skipping.")
        return

    insert_price_history(
        game_id=game["id"],
        price=price_data["price"],
        regular_price=price_data["regular_price"],
        store=price_data["store"],
    )

    historical_low = get_historical_low(game["id"])
    is_deal = historical_low is not None and price_data["price"] <= historical_low

    if not is_deal:
        print(f"[{game['title']}] Current price ${price_data['price']} is not a deal.")
        return

    if was_recently_notified(game["id"]):
        print(f"[{game['title']}] Already notified recently, skipping.")
        return

    provider = get_provider()
    commentary = provider.generate_text(
        f"Write a one-sentence buy recommendation for '{game['title']}'. "
        f"Current price: ${price_data['price']} on {price_data['store']} "
        f"({price_data['cut']}% off). Historical low: ${historical_low}."
    )

    send_deal_alert(
        game_title=game["title"],
        price=price_data["price"],
        regular_price=price_data["regular_price"],
        store=price_data["store"],
        cut=price_data["cut"],
        ai_commentary=commentary,
    )
    log_notification(game["id"], price_data["price"])
    print(f"[{game['title']}] Deal alert sent!")


def run() -> None:
    games = get_games()
    print(f"Checking prices for {len(games)} game(s)...")
    for game in games:
        process_game(game)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cron.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add cron/price_check.py tests/test_cron.py
git commit -m "feat: cron worker — price check, deal detection, alert dispatch"
```

---

## Task 9: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/price_check.yml`

- [ ] **Step 1: Create `.github/workflows/price_check.yml`**

```yaml
name: Price Check

on:
  schedule:
    - cron: "0 */12 * * *"   # every 12 hours — change to adjust frequency
  workflow_dispatch:          # allow manual trigger from GitHub UI

jobs:
  check-prices:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run price check
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          ITAD_API_KEY: ${{ secrets.ITAD_API_KEY }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          AI_PROVIDER: ${{ secrets.AI_PROVIDER }}
        run: python -m cron.price_check
```

- [ ] **Step 2: Add all required secrets to GitHub repository**

Go to: GitHub repo → Settings → Secrets and variables → Actions → New repository secret

Add each secret from `.env.example` (except `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` — those are only used by the bot).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/price_check.yml
git commit -m "feat: GitHub Actions cron workflow for price checks"
```

---

## Task 10: Bot Function Tools

**Files:**
- Create: `bot/functions.py`
- Create: `tests/test_bot_functions.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bot_functions.py
from unittest.mock import patch


def test_add_game_success(mocker):
    from bot.functions import add_game
    mocker.patch("bot.functions.search_game", return_value={"id": "abc123", "title": "Elden Ring"})
    mocker.patch("bot.functions.db_add_game", return_value={"title": "Elden Ring"})
    result = add_game("Elden Ring")
    assert "Elden Ring" in result
    assert "tracking" in result.lower()


def test_add_game_not_found(mocker):
    from bot.functions import add_game
    mocker.patch("bot.functions.search_game", return_value=None)
    result = add_game("Nonexistent XYZ 99999")
    assert "not found" in result.lower()


def test_remove_game_success(mocker):
    from bot.functions import remove_game
    mocker.patch("bot.functions.db_remove_game", return_value=True)
    result = remove_game("Elden Ring")
    assert "removed" in result.lower() or "no longer tracking" in result.lower()


def test_remove_game_not_found(mocker):
    from bot.functions import remove_game
    mocker.patch("bot.functions.db_remove_game", return_value=False)
    result = remove_game("Unknown Game")
    assert "not found" in result.lower() or "wasn't" in result.lower()


def test_list_games_with_games(mocker):
    from bot.functions import list_games
    mocker.patch("bot.functions.db_get_games", return_value=[
        {"title": "Elden Ring"},
        {"title": "Hollow Knight"},
    ])
    result = list_games()
    assert "Elden Ring" in result
    assert "Hollow Knight" in result


def test_list_games_empty(mocker):
    from bot.functions import list_games
    mocker.patch("bot.functions.db_get_games", return_value=[])
    result = list_games()
    assert "no games" in result.lower() or "empty" in result.lower()


def test_get_current_price_success(mocker):
    from bot.functions import get_current_price
    mocker.patch("bot.functions.search_game", return_value={"id": "abc123", "title": "Hades"})
    mocker.patch("bot.functions.get_best_price", return_value={
        "price": 9.99, "regular_price": 24.99, "store": "Steam", "cut": 60
    })
    result = get_current_price("Hades")
    assert "9.99" in result
    assert "Steam" in result


def test_get_current_price_not_found(mocker):
    from bot.functions import get_current_price
    mocker.patch("bot.functions.search_game", return_value=None)
    result = get_current_price("Unknown Game")
    assert "not found" in result.lower()


def test_get_recent_deals_with_results(mocker):
    from bot.functions import get_recent_deals
    mocker.patch("bot.functions.db_get_recent_deals", return_value=[
        {"price": 9.99, "notified_at": "2026-04-04T00:00:00+00:00", "games": {"title": "Hades"}}
    ])
    result = get_recent_deals()
    assert "Hades" in result
    assert "9.99" in result


def test_get_recent_deals_empty(mocker):
    from bot.functions import get_recent_deals
    mocker.patch("bot.functions.db_get_recent_deals", return_value=[])
    result = get_recent_deals()
    assert "no recent" in result.lower() or "no deals" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_bot_functions.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `bot/functions.py`**

```python
from utils.itad import search_game, get_best_price
from db.client import (
    add_game as db_add_game,
    remove_game as db_remove_game,
    get_games as db_get_games,
    get_recent_deals as db_get_recent_deals,
)


def add_game(title: str) -> str:
    game = search_game(title)
    if game is None:
        return f"Sorry, I couldn't find '{title}' on IsThereAnyDeal."
    db_add_game(game["title"], game["id"])
    return f"Now tracking **{game['title']}**. I'll alert you when a deal drops."


def remove_game(title: str) -> str:
    removed = db_remove_game(title)
    if removed:
        return f"No longer tracking **{title}**."
    return f"**{title}** wasn't in your watchlist."


def list_games() -> str:
    games = db_get_games()
    if not games:
        return "Your watchlist is empty. Try 'track <game name>' to add a game."
    lines = "\n".join(f"• {g['title']}" for g in games)
    return f"**Games you're tracking:**\n{lines}"


def get_current_price(title: str) -> str:
    game = search_game(title)
    if game is None:
        return f"Sorry, I couldn't find '{title}' on IsThereAnyDeal."
    price_data = get_best_price(game["id"])
    if price_data is None:
        return f"No current deals found for **{game['title']}**."
    return (
        f"**{game['title']}** — best price: ${price_data['price']:.2f} on {price_data['store']} "
        f"({price_data['cut']}% off, was ${price_data['regular_price']:.2f})"
    )


def get_recent_deals() -> str:
    deals = db_get_recent_deals()
    if not deals:
        return "No recent deals found."
    lines = "\n".join(
        f"• **{d['games']['title']}** — ${d['price']:.2f} (alerted {d['notified_at'][:10]})"
        for d in deals
    )
    return f"**Recent deals I found:**\n{lines}"


# Tool definitions in OpenAI function-calling format (used by both Groq and Gemini wrappers)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_game",
            "description": "Add a game to the watchlist to track its price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The name of the game to track."}
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_game",
            "description": "Remove a game from the watchlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The name of the game to remove."}
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_games",
            "description": "List all games currently on the watchlist.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_price",
            "description": "Get the current best price for a game across all stores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The name of the game to look up."}
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_deals",
            "description": "Show recent deal alerts that were sent.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_FUNCTION_MAP = {
    "add_game": add_game,
    "remove_game": remove_game,
    "list_games": list_games,
    "get_current_price": get_current_price,
    "get_recent_deals": get_recent_deals,
}


def dispatch(name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments."""
    fn = _FUNCTION_MAP.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    return fn(**arguments)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_bot_functions.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/functions.py tests/test_bot_functions.py
git commit -m "feat: Discord bot function-calling tools and dispatch"
```

---

## Task 11: Discord Bot Client

**Files:**
- Create: `bot/client.py`

- [ ] **Step 1: Implement `bot/client.py`**

> Note: discord.py's `on_message` is event-driven and tightly coupled to the Discord gateway. Integration testing requires a live bot token — unit tests for this layer are skipped in favour of manual smoke testing after deployment.

```python
import os
import discord
from dotenv import load_dotenv
from ai import get_provider
from bot.functions import TOOLS, dispatch

load_dotenv()

_CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])

_SYSTEM_PROMPT = (
    "You are DropHunter, a personal game deal assistant. "
    "When the user asks you to track, untrack, list games, check prices, or see recent deals, "
    "use the available tools. For anything else, respond helpfully in plain text."
)

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    print(f"DropHunter bot ready as {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.channel.id != _CHANNEL_ID:
        return

    provider = get_provider()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": message.content},
    ]

    async with message.channel.typing():
        result = provider.chat_with_tools(messages=messages, tools=TOOLS)

        if "tool_calls" in result:
            tool_responses = []
            for tc in result["tool_calls"]:
                tool_result = dispatch(tc["name"], tc["arguments"])
                tool_responses.append(tool_result)

            # Feed tool results back to AI for a natural summary
            messages.append({"role": "assistant", "content": str(result)})
            messages.append({"role": "user", "content": f"Tool results: {'; '.join(tool_responses)}"})
            final = provider.chat_with_tools(messages=messages, tools=[])
            reply = final.get("text", "\n".join(tool_responses))
        else:
            reply = result.get("text", "I'm not sure how to help with that.")

    await message.channel.send(reply)


def run():
    bot.run(os.environ["DISCORD_BOT_TOKEN"])
```

- [ ] **Step 2: Commit**

```bash
git add bot/client.py
git commit -m "feat: Discord bot client with natural language + function calling"
```

---

## Task 12: Entry Point and Final Wiring

**Files:**
- Create: `main.py`

- [ ] **Step 1: Create `main.py`**

```python
from bot.client import run

if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Run all tests to confirm full suite passes**

```bash
pytest -v
```

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: main.py bot entry point"
```

---

## Task 13: Deployment to Railway

- [ ] **Step 1: Create a `Procfile` for Railway/Render**

```
worker: python main.py
```

- [ ] **Step 2: Commit**

```bash
git add Procfile
git commit -m "chore: Procfile for Railway/Render deployment"
```

- [ ] **Step 3: Deploy to Railway**

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Select the DropHunter repo
3. Set all environment variables in Railway dashboard (same as `.env.example`, excluding GitHub Actions-only secrets)
4. Railway will detect the `Procfile` and run `python main.py` as the worker process

- [ ] **Step 4: Smoke test the bot**

In your Discord channel, send:
- `What games am I tracking?` → should reply with empty watchlist message
- `Track Hades` → should confirm tracking
- `What games am I tracking?` → should list Hades
- `What's the best price for Hades right now?` → should return current price from ITAD
- `Stop tracking Hades` → should confirm removal

- [ ] **Step 5: Trigger cron manually to verify end-to-end**

In GitHub → Actions → Price Check → Run workflow → confirm it runs without errors.
