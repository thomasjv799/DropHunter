# DropHunter Discord Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the interactive Discord bot that accepts natural language commands (e.g. "Track Elden Ring", "What games am I watching?") and dispatches them to Groq/Gemini via function calling, backed by the same Supabase database used by the cron worker.

**Architecture:** `main.py` creates a `discord.py` bot that listens to a single configured channel. Each incoming message is forwarded to the AI provider with 5 callable tools exposed. The AI selects and calls the appropriate tool, which maps to `bot/functions.py` helpers that query Supabase and/or the ITAD API. Responses are posted back to the same channel. The bot runs as a long-lived process on Railway or Render free tier.

**Tech Stack:** Python 3.12, discord.py, supabase-py, groq, google-generativeai, python-dotenv, pytest

**Prerequisite:** Plan 1 (Foundation + Cron Worker) must be fully implemented. This plan reuses `db/client.py`, `utils/itad.py`, `ai/base.py`, `ai/groq_provider.py`, `ai/gemini_provider.py`, and `ai/factory.py` without modification.

---

## File Map

| File | Responsibility |
|---|---|
| `bot/__init__.py` | Empty package marker |
| `bot/functions.py` | The 5 callable tools: `add_game`, `remove_game`, `list_games`, `get_current_price`, `get_recent_deals` |
| `bot/client.py` | Discord bot setup, message listener, AI dispatch loop |
| `main.py` | Entry point: loads env, creates clients, starts bot |
| `tests/test_bot_functions.py` | Tests for `bot/functions.py` |
| `tests/test_bot_client.py` | Tests for `bot/client.py` message dispatch logic |

---

### Task 1: Bot Function Tools

**Files:**
- Create: `bot/__init__.py`
- Create: `bot/functions.py`
- Create: `tests/test_bot_functions.py`

These are the 5 functions the AI can invoke. Each takes a Supabase client (and optionally an ITAD key) and returns a plain string suitable for sending back to Discord.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bot_functions.py
from unittest.mock import MagicMock, patch

import pytest

from bot.functions import (
    add_game,
    get_current_price,
    get_recent_deals,
    list_games,
    remove_game,
)


@pytest.fixture
def mock_db():
    return MagicMock()


def test_add_game_success(mock_db):
    with patch("bot.functions.search_game", return_value="itad-id-123"):
        with patch("bot.functions.db_add_game", return_value=[{"id": "uuid", "title": "Elden Ring"}]):
            result = add_game(mock_db, "Elden Ring", itad_key="testkey")
    assert "Elden Ring" in result
    assert "now tracking" in result.lower()


def test_add_game_not_found_on_itad(mock_db):
    with patch("bot.functions.search_game", return_value=None):
        result = add_game(mock_db, "Nonexistent Game XYZ", itad_key="testkey")
    assert "not found" in result.lower()


def test_remove_game_success(mock_db):
    with patch("bot.functions.db_remove_game", return_value=[{"id": "uuid"}]):
        result = remove_game(mock_db, "Elden Ring")
    assert "Elden Ring" in result
    assert "removed" in result.lower()


def test_list_games_with_games(mock_db):
    with patch("bot.functions.db_list_games", return_value=[
        {"title": "Elden Ring"},
        {"title": "Hades"},
    ]):
        result = list_games(mock_db)
    assert "Elden Ring" in result
    assert "Hades" in result


def test_list_games_empty(mock_db):
    with patch("bot.functions.db_list_games", return_value=[]):
        result = list_games(mock_db)
    assert "not tracking" in result.lower() or "no games" in result.lower()


def test_get_current_price_found(mock_db):
    mock_price = MagicMock(price=14.99, regular_price=59.99, store="Steam", cut=75)
    with patch("bot.functions.search_game", return_value="itad-id-123"):
        with patch("bot.functions.get_best_price", return_value=mock_price):
            result = get_current_price(mock_db, "Elden Ring", itad_key="testkey")
    assert "14.99" in result
    assert "Steam" in result
    assert "75%" in result


def test_get_current_price_not_found_on_itad(mock_db):
    with patch("bot.functions.search_game", return_value=None):
        result = get_current_price(mock_db, "Nonexistent Game", itad_key="testkey")
    assert "not found" in result.lower()


def test_get_current_price_no_deals(mock_db):
    with patch("bot.functions.search_game", return_value="itad-id-123"):
        with patch("bot.functions.get_best_price", return_value=None):
            result = get_current_price(mock_db, "Some Game", itad_key="testkey")
    assert "no price" in result.lower() or "unavailable" in result.lower()


def test_get_recent_deals_with_results(mock_db):
    with patch("bot.functions.db_get_recent_deals", return_value=[
        {"games": {"title": "Hades"}, "price": 4.99, "notified_at": "2026-04-04T12:00:00"},
        {"games": {"title": "Celeste"}, "price": 3.99, "notified_at": "2026-04-03T06:00:00"},
    ]):
        result = get_recent_deals(mock_db)
    assert "Hades" in result
    assert "4.99" in result
    assert "Celeste" in result


def test_get_recent_deals_empty(mock_db):
    with patch("bot.functions.db_get_recent_deals", return_value=[]):
        result = get_recent_deals(mock_db)
    assert "no recent" in result.lower() or "no deals" in result.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_bot_functions.py -v`
Expected: `ModuleNotFoundError: No module named 'bot.functions'`

- [ ] **Step 3: Create `bot/__init__.py`**

Create empty file: `bot/__init__.py`

- [ ] **Step 4: Implement `bot/functions.py`**

```python
# bot/functions.py
from db.client import (
    add_game as db_add_game,
    get_recent_deals as db_get_recent_deals,
    list_games as db_list_games,
    remove_game as db_remove_game,
)
from utils.itad import get_best_price, search_game


def add_game(db, title: str, itad_key: str) -> str:
    itad_id = search_game(title, api_key=itad_key)
    if itad_id is None:
        return f'"{title}" was not found on IsThereAnyDeal. Try a different title.'
    db_add_game(db, title, itad_id)
    return f'Now tracking **{title}**. I\'ll alert you when it hits a new low price.'


def remove_game(db, title: str) -> str:
    db_remove_game(db, title)
    return f'Removed **{title}** from your watchlist.'


def list_games(db) -> str:
    games = db_list_games(db)
    if not games:
        return "You're not tracking any games yet. Say \"Track <game name>\" to add one."
    titles = "\n".join(f"- {g['title']}" for g in games)
    return f"Currently tracking {len(games)} game(s):\n{titles}"


def get_current_price(db, title: str, itad_key: str) -> str:
    itad_id = search_game(title, api_key=itad_key)
    if itad_id is None:
        return f'"{title}" was not found on IsThereAnyDeal.'
    best = get_best_price(itad_id, api_key=itad_key)
    if best is None:
        return f'No price data available for **{title}** right now.'
    return (
        f'**{title}** — best price: **${best.price:.2f}** on {best.store} '
        f'({best.cut}% off regular ${best.regular_price:.2f})'
    )


def get_recent_deals(db) -> str:
    deals = db_get_recent_deals(db)
    if not deals:
        return "No recent deals found."
    lines = [
        f"- **{d['games']['title']}** — ${d['price']:.2f} (alerted {d['notified_at'][:10]})"
        for d in deals
    ]
    return "Recent deals:\n" + "\n".join(lines)
```

- [ ] **Step 5: Run tests to confirm they pass**

Run: `pytest tests/test_bot_functions.py -v`
Expected: 10 passed

- [ ] **Step 6: Lint and format**

Run: `ruff check bot/functions.py tests/test_bot_functions.py && ruff format bot/functions.py tests/test_bot_functions.py`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add bot/__init__.py bot/functions.py tests/test_bot_functions.py
git commit -m "feat: add Discord bot function-calling tools"
```

---

### Task 2: Discord Bot Client

**Files:**
- Create: `bot/client.py`
- Create: `tests/test_bot_client.py`

The client sets up the Discord bot, listens for messages in the configured channel, and runs an AI dispatch loop: send the user message + tool definitions to the AI, execute whatever tool the AI calls, then send the AI's final response back to Discord.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bot_client.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.client import dispatch


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_ai():
    return MagicMock()


@pytest.mark.asyncio
async def test_dispatch_calls_list_games_tool(mock_db, mock_ai):
    mock_ai.chat_with_tools.return_value = "You are tracking 2 games:\n- Hades\n- Celeste"

    result = await dispatch(
        user_message="What games am I tracking?",
        db=mock_db,
        ai=mock_ai,
        itad_key="testkey",
    )

    mock_ai.chat_with_tools.assert_called_once()
    assert "Hades" in result or len(result) > 0


@pytest.mark.asyncio
async def test_dispatch_returns_string(mock_db, mock_ai):
    mock_ai.chat_with_tools.return_value = "Now tracking Elden Ring."
    result = await dispatch(
        user_message="Track Elden Ring",
        db=mock_db,
        ai=mock_ai,
        itad_key="testkey",
    )
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_dispatch_passes_tools_to_ai(mock_db, mock_ai):
    mock_ai.chat_with_tools.return_value = "Done."
    await dispatch(
        user_message="Remove Hades",
        db=mock_db,
        ai=mock_ai,
        itad_key="testkey",
    )
    call_kwargs = mock_ai.chat_with_tools.call_args.kwargs
    tool_names = [t["name"] for t in call_kwargs["tools"]]
    assert "add_game" in tool_names
    assert "remove_game" in tool_names
    assert "list_games" in tool_names
    assert "get_current_price" in tool_names
    assert "get_recent_deals" in tool_names
```

- [ ] **Step 2: Install pytest-asyncio**

Run: `pip install pytest-asyncio`

Add to `requirements.txt`:
```
pytest-asyncio==0.24.0
```

Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Run tests to confirm they fail**

Run: `pytest tests/test_bot_client.py -v`
Expected: `ModuleNotFoundError: No module named 'bot.client'`

- [ ] **Step 4: Add `chat_with_tools` to `AIProvider` base class**

Edit `ai/base.py` to add the new abstract method:

```python
# ai/base.py
from abc import ABC, abstractmethod
from collections.abc import Callable


class AIProvider(ABC):
    @abstractmethod
    def recommend(
        self,
        game_title: str,
        price: float,
        regular_price: float,
        store: str,
        cut: int,
    ) -> str: ...

    @abstractmethod
    def chat_with_tools(
        self,
        user_message: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], str],
    ) -> str: ...
```

- [ ] **Step 5: Implement `chat_with_tools` in `ai/groq_provider.py`**

Replace the entire file with:

```python
# ai/groq_provider.py
import json
from collections.abc import Callable

from groq import Groq

from ai.base import AIProvider


class GroqProvider(AIProvider):
    def __init__(self, client: Groq) -> None:
        self._client = client

    def recommend(
        self,
        game_title: str,
        price: float,
        regular_price: float,
        store: str,
        cut: int,
    ) -> str:
        prompt = (
            f"{game_title} is {cut}% off on {store} for ${price:.2f} "
            f"(regular ${regular_price:.2f}). "
            "In one short sentence, is this a good deal and should I buy it now?"
        )
        response = self._client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
        )
        return response.choices[0].message.content.strip()

    def chat_with_tools(
        self,
        user_message: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], str],
    ) -> str:
        messages = [{"role": "user", "content": user_message}]
        groq_tools = [
            {"type": "function", "function": t} for t in tools
        ]

        while True:
            response = self._client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                tools=groq_tools,
                tool_choice="auto",
            )
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls":
                messages.append(choice.message)
                for tool_call in choice.message.tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    result = tool_executor(tool_call.function.name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
            else:
                return choice.message.content.strip()
```

- [ ] **Step 6: Implement `chat_with_tools` in `ai/gemini_provider.py`**

Replace the entire file with:

```python
# ai/gemini_provider.py
import json
from collections.abc import Callable

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

from ai.base import AIProvider


def _to_gemini_tool(tool_def: dict) -> Tool:
    params = tool_def.get("parameters", {})
    return Tool(function_declarations=[
        FunctionDeclaration(
            name=tool_def["name"],
            description=tool_def.get("description", ""),
            parameters=params,
        )
    ])


class GeminiProvider(AIProvider):
    def __init__(self, model: genai.GenerativeModel) -> None:
        self._model = model

    def recommend(
        self,
        game_title: str,
        price: float,
        regular_price: float,
        store: str,
        cut: int,
    ) -> str:
        prompt = (
            f"{game_title} is {cut}% off on {store} for ${price:.2f} "
            f"(regular ${regular_price:.2f}). "
            "In one short sentence, is this a good deal and should I buy it now?"
        )
        return self._model.generate_content(prompt).text.strip()

    def chat_with_tools(
        self,
        user_message: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], str],
    ) -> str:
        gemini_tools = [_to_gemini_tool(t) for t in tools]
        chat = self._model.start_chat()

        response = chat.send_message(user_message, tools=gemini_tools)

        while response.candidates[0].content.parts[0].function_call.name:
            fc = response.candidates[0].content.parts[0].function_call
            result = tool_executor(fc.name, dict(fc.args))
            response = chat.send_message(
                genai.protos.Content(
                    parts=[genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fc.name,
                            response={"result": result},
                        )
                    )]
                )
            )

        return response.text.strip()
```

- [ ] **Step 7: Implement `bot/client.py`**

```python
# bot/client.py
import os

import discord

from bot.functions import (
    add_game,
    get_current_price,
    get_recent_deals,
    list_games,
    remove_game,
)

TOOLS = [
    {
        "name": "add_game",
        "description": "Search for a game on IsThereAnyDeal and add it to the watchlist.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The game title to search for and track"}
            },
            "required": ["title"],
        },
    },
    {
        "name": "remove_game",
        "description": "Remove a game from the watchlist.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The game title to stop tracking"}
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_games",
        "description": "List all games currently on the watchlist.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_current_price",
        "description": "Look up the current best price for a game across all stores.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The game title to look up"}
            },
            "required": ["title"],
        },
    },
    {
        "name": "get_recent_deals",
        "description": "Show recently detected deals from the notifications log.",
        "parameters": {"type": "object", "properties": {}},
    },
]


async def dispatch(user_message: str, db, ai, itad_key: str) -> str:
    def tool_executor(name: str, args: dict) -> str:
        if name == "add_game":
            return add_game(db, args["title"], itad_key=itad_key)
        if name == "remove_game":
            return remove_game(db, args["title"])
        if name == "list_games":
            return list_games(db)
        if name == "get_current_price":
            return get_current_price(db, args["title"], itad_key=itad_key)
        if name == "get_recent_deals":
            return get_recent_deals(db)
        return f"Unknown tool: {name}"

    return ai.chat_with_tools(
        user_message=user_message,
        tools=TOOLS,
        tool_executor=tool_executor,
    )


def create_bot(db, ai, itad_key: str, channel_id: int) -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        print(f"DropHunter bot ready as {bot.user}")

    @bot.event
    async def on_message(message: discord.Message):
        if message.author == bot.user:
            return
        if message.channel.id != channel_id:
            return
        async with message.channel.typing():
            response = await dispatch(message.content, db=db, ai=ai, itad_key=itad_key)
        await message.channel.send(response)

    return bot
```

- [ ] **Step 8: Run tests to confirm they pass**

Run: `pytest tests/test_bot_client.py -v`
Expected: 3 passed

- [ ] **Step 9: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

- [ ] **Step 10: Lint and format**

Run: `ruff check bot/client.py ai/groq_provider.py ai/gemini_provider.py ai/base.py tests/test_bot_client.py && ruff format bot/client.py ai/groq_provider.py ai/gemini_provider.py ai/base.py tests/test_bot_client.py`
Expected: No errors

- [ ] **Step 11: Commit**

```bash
git add bot/client.py ai/base.py ai/groq_provider.py ai/gemini_provider.py tests/test_bot_client.py requirements.txt pyproject.toml
git commit -m "feat: add Discord bot client with AI function-calling dispatch loop"
```

---

### Task 3: Main Entry Point

**Files:**
- Create: `main.py`

- [ ] **Step 1: Create `main.py`**

```python
# main.py
import os

from dotenv import load_dotenv

from ai.factory import get_provider
from bot.client import create_bot
from db.client import get_client

load_dotenv()

db = get_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
ai = get_provider()
itad_key = os.environ["ITAD_API_KEY"]
channel_id = int(os.environ["DISCORD_CHANNEL_ID"])
bot_token = os.environ["DISCORD_BOT_TOKEN"]

bot = create_bot(db=db, ai=ai, itad_key=itad_key, channel_id=channel_id)
bot.run(bot_token)
```

- [ ] **Step 2: Smoke test locally**

Copy `.env.example` to `.env` and fill in real values, then:

Run: `python main.py`
Expected: `DropHunter bot ready as <BotName>#1234` — bot appears online in Discord

Test by typing in the configured channel:
- `What games am I tracking?` → lists watchlist (empty initially)
- `Track Celeste` → confirms tracking Celeste
- `What's the best price for Celeste?` → returns current price from ITAD

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add main.py entry point for Discord bot"
```

---

## Deployment (Railway or Render)

After all tests pass and the bot works locally:

1. Push to GitHub: `git push origin main`
2. On Railway: **New Project → Deploy from GitHub repo → select DropHunter**
   - Set start command: `python main.py`
   - Add all env vars from `.env.example` under **Variables**
3. On Render: **New Web Service → Connect repo**
   - Build command: `pip install -r requirements.txt`
   - Start command: `python main.py`
   - Add env vars under **Environment**

The bot will start automatically and stay online indefinitely on the free tier.
