# DropHunter Foundation + Cron Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared Python foundation (database layer, ITAD API wrapper, AI provider abstraction, Discord webhook helper) and the GitHub Actions cron worker that monitors game prices every 12 hours and sends Discord alerts when a deal is detected.

**Architecture:** A stateless `cron/price_check.py` script runs on GitHub Actions every 12h. It reads the watchlist from Supabase, fetches current prices from IsThereAnyDeal, inserts price history, detects deals (current price ≤ historical low), calls an AI provider for a one-sentence buy recommendation, and POSTs a Discord webhook notification. All state lives in Supabase; all secrets are GitHub Actions secrets injected as env vars.

**Tech Stack:** Python 3.12, supabase-py, requests, groq, google-generativeai, python-dotenv, pytest, ruff

---

## File Map

| File | Responsibility |
|---|---|
| `requirements.txt` | All Python dependencies |
| `.env.example` | Template for required environment variables |
| `pyproject.toml` | Ruff linter/formatter config + pytest config |
| `db/__init__.py` | Empty package marker |
| `db/client.py` | Supabase client factory + all query helpers |
| `utils/__init__.py` | Empty package marker |
| `utils/itad.py` | IsThereAnyDeal API wrapper: search + best price |
| `utils/discord.py` | Discord webhook POST helper |
| `ai/__init__.py` | Empty package marker |
| `ai/base.py` | Abstract `AIProvider` interface |
| `ai/groq_provider.py` | Groq implementation of `AIProvider` |
| `ai/gemini_provider.py` | Gemini implementation of `AIProvider` |
| `ai/factory.py` | Reads `AI_PROVIDER` env var, returns the right provider |
| `cron/__init__.py` | Empty package marker |
| `cron/price_check.py` | Main cron script: full pipeline orchestration |
| `.github/workflows/price_check.yml` | GitHub Actions cron workflow |
| `tests/__init__.py` | Empty package marker |
| `tests/test_db.py` | Tests for `db/client.py` |
| `tests/test_itad.py` | Tests for `utils/itad.py` |
| `tests/test_discord.py` | Tests for `utils/discord.py` |
| `tests/test_ai.py` | Tests for all AI providers and factory |
| `tests/test_price_check.py` | Tests for `cron/price_check.py` |

---

### Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `pyproject.toml`
- Create: `db/__init__.py`, `utils/__init__.py`, `ai/__init__.py`, `cron/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
supabase==2.9.1
requests==2.32.3
groq==0.13.0
google-generativeai==0.8.3
python-dotenv==1.0.1
pytest==8.3.4
ruff==0.9.0
```

- [ ] **Step 2: Create `.env.example`**

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
ITAD_API_KEY=your-itad-api-key
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy
DISCORD_BOT_TOKEN=your-discord-bot-token
DISCORD_CHANNEL_ID=123456789012345678
GROQ_API_KEY=your-groq-api-key
GEMINI_API_KEY=your-gemini-api-key
AI_PROVIDER=groq
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Create all empty `__init__.py` files**

Create empty files at: `db/__init__.py`, `utils/__init__.py`, `ai/__init__.py`, `cron/__init__.py`, `tests/__init__.py`

- [ ] **Step 5: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example pyproject.toml db/__init__.py utils/__init__.py ai/__init__.py cron/__init__.py tests/__init__.py
git commit -m "chore: project setup — dependencies, directory structure, tooling config"
```

---

### Task 2: Database Client

**Files:**
- Create: `db/client.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db.py
import pytest
from unittest.mock import MagicMock
from db.client import (
    get_client,
    get_games,
    add_game,
    remove_game,
    list_games,
    insert_price_history,
    get_historical_low,
    was_notified_recently,
    log_notification,
    get_recent_deals,
)


@pytest.fixture
def mock_supabase():
    return MagicMock()


def test_get_games_returns_list(mock_supabase):
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = [
        {"id": "abc", "title": "Elden Ring", "itad_id": "elden-ring"}
    ]
    result = get_games(mock_supabase)
    assert result == [{"id": "abc", "title": "Elden Ring", "itad_id": "elden-ring"}]
    mock_supabase.table.assert_called_with("games")


def test_get_games_returns_empty_list(mock_supabase):
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = []
    assert get_games(mock_supabase) == []


def test_add_game_inserts_row(mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "new-uuid", "title": "Hades", "itad_id": "hades"}
    ]
    result = add_game(mock_supabase, "Hades", "hades")
    mock_supabase.table.assert_called_with("games")
    mock_supabase.table.return_value.insert.assert_called_with({"title": "Hades", "itad_id": "hades"})
    assert result[0]["title"] == "Hades"


def test_remove_game_deletes_by_title(mock_supabase):
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []
    remove_game(mock_supabase, "Hades")
    mock_supabase.table.assert_called_with("games")
    mock_supabase.table.return_value.delete.return_value.eq.assert_called_with("title", "Hades")


def test_list_games_returns_all(mock_supabase):
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = [
        {"id": "1", "title": "Hades", "itad_id": "hades"},
        {"id": "2", "title": "Celeste", "itad_id": "celeste"},
    ]
    assert len(list_games(mock_supabase)) == 2


def test_insert_price_history(mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "h1"}]
    result = insert_price_history(mock_supabase, "game-uuid", 9.99, 19.99, "Steam")
    mock_supabase.table.assert_called_with("price_history")
    mock_supabase.table.return_value.insert.assert_called_with({
        "game_id": "game-uuid",
        "price": 9.99,
        "regular_price": 19.99,
        "store": "Steam",
    })
    assert result == [{"id": "h1"}]


def test_get_historical_low_returns_price(mock_supabase):
    (mock_supabase.table.return_value.select.return_value
     .eq.return_value.order.return_value.limit.return_value.execute.return_value.data) = [{"price": 4.99}]
    assert get_historical_low(mock_supabase, "game-uuid") == 4.99


def test_get_historical_low_returns_none_when_empty(mock_supabase):
    (mock_supabase.table.return_value.select.return_value
     .eq.return_value.order.return_value.limit.return_value.execute.return_value.data) = []
    assert get_historical_low(mock_supabase, "game-uuid") is None


def test_was_notified_recently_true(mock_supabase):
    (mock_supabase.table.return_value.select.return_value
     .eq.return_value.gte.return_value.execute.return_value.data) = [{"id": "n1"}]
    assert was_notified_recently(mock_supabase, "game-uuid") is True


def test_was_notified_recently_false(mock_supabase):
    (mock_supabase.table.return_value.select.return_value
     .eq.return_value.gte.return_value.execute.return_value.data) = []
    assert was_notified_recently(mock_supabase, "game-uuid") is False


def test_log_notification(mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "n1"}]
    log_notification(mock_supabase, "game-uuid", 9.99)
    mock_supabase.table.assert_called_with("notifications_log")
    mock_supabase.table.return_value.insert.assert_called_with({"game_id": "game-uuid", "price": 9.99})


def test_get_recent_deals(mock_supabase):
    (mock_supabase.table.return_value.select.return_value
     .order.return_value.limit.return_value.execute.return_value.data) = [
        {"id": "n1", "games": {"title": "Elden Ring"}, "price": 19.99}
    ]
    result = get_recent_deals(mock_supabase)
    assert len(result) == 1
    assert result[0]["games"]["title"] == "Elden Ring"
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_db.py -v`
Expected: `ModuleNotFoundError: No module named 'db.client'`

- [ ] **Step 3: Implement `db/client.py`**

```python
# db/client.py
from datetime import datetime, timedelta, timezone

from supabase import Client, create_client


def get_client(url: str, key: str) -> Client:
    return create_client(url, key)


def get_games(client: Client) -> list[dict]:
    return client.table("games").select("*").execute().data


def add_game(client: Client, title: str, itad_id: str) -> list[dict]:
    return client.table("games").insert({"title": title, "itad_id": itad_id}).execute().data


def remove_game(client: Client, title: str) -> list[dict]:
    return client.table("games").delete().eq("title", title).execute().data


def list_games(client: Client) -> list[dict]:
    return client.table("games").select("*").execute().data


def insert_price_history(
    client: Client,
    game_id: str,
    price: float,
    regular_price: float,
    store: str,
) -> list[dict]:
    return (
        client.table("price_history")
        .insert({"game_id": game_id, "price": price, "regular_price": regular_price, "store": store})
        .execute()
        .data
    )


def get_historical_low(client: Client, game_id: str) -> float | None:
    result = (
        client.table("price_history")
        .select("price")
        .eq("game_id", game_id)
        .order("price")
        .limit(1)
        .execute()
    )
    return result.data[0]["price"] if result.data else None


def was_notified_recently(client: Client, game_id: str, hours: int = 12) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = (
        client.table("notifications_log")
        .select("id")
        .eq("game_id", game_id)
        .gte("notified_at", cutoff)
        .execute()
    )
    return len(result.data) > 0


def log_notification(client: Client, game_id: str, price: float) -> list[dict]:
    return (
        client.table("notifications_log")
        .insert({"game_id": game_id, "price": price})
        .execute()
        .data
    )


def get_recent_deals(client: Client, limit: int = 10) -> list[dict]:
    return (
        client.table("notifications_log")
        .select("*, games(title)")
        .order("notified_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_db.py -v`
Expected: 12 passed

- [ ] **Step 5: Lint and format**

Run: `ruff check db/client.py tests/test_db.py && ruff format db/client.py tests/test_db.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add db/client.py tests/test_db.py
git commit -m "feat: add Supabase database client with query helpers"
```

---

### Task 3: ITAD API Wrapper

**Files:**
- Create: `utils/itad.py`
- Create: `tests/test_itad.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_itad.py
from unittest.mock import MagicMock, patch

import pytest

from utils.itad import BestPrice, get_best_price, search_game


def test_search_game_returns_itad_id():
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"id": "018d937f-b657-728b-aa4e-e3b8e4a8d422", "slug": "elden-ring", "title": "Elden Ring"}
    ]
    with patch("utils.itad.requests.get", return_value=mock_resp):
        result = search_game("Elden Ring", api_key="testkey")
    assert result == "018d937f-b657-728b-aa4e-e3b8e4a8d422"


def test_search_game_returns_none_when_not_found():
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    with patch("utils.itad.requests.get", return_value=mock_resp):
        result = search_game("Nonexistent Game XYZ", api_key="testkey")
    assert result is None


def test_get_best_price_returns_cheapest_deal():
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {
            "id": "game-id-1",
            "deals": [
                {
                    "shop": {"name": "Steam"},
                    "price": {"amount": 29.99},
                    "regular": {"amount": 59.99},
                    "cut": 50,
                },
                {
                    "shop": {"name": "GOG"},
                    "price": {"amount": 24.99},
                    "regular": {"amount": 59.99},
                    "cut": 58,
                },
            ],
        }
    ]
    with patch("utils.itad.requests.post", return_value=mock_resp):
        result = get_best_price("game-id-1", api_key="testkey")
    assert result is not None
    assert result.price == 24.99
    assert result.store == "GOG"
    assert result.regular_price == 59.99
    assert result.cut == 58


def test_get_best_price_returns_none_when_no_deals():
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"id": "game-id-1", "deals": []}]
    with patch("utils.itad.requests.post", return_value=mock_resp):
        assert get_best_price("game-id-1", api_key="testkey") is None


def test_get_best_price_returns_none_when_game_missing_from_response():
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    with patch("utils.itad.requests.post", return_value=mock_resp):
        assert get_best_price("game-id-1", api_key="testkey") is None
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_itad.py -v`
Expected: `ModuleNotFoundError: No module named 'utils.itad'`

- [ ] **Step 3: Implement `utils/itad.py`**

```python
# utils/itad.py
from dataclasses import dataclass

import requests

ITAD_BASE = "https://api.isthereanydeal.com"


@dataclass
class BestPrice:
    price: float
    regular_price: float
    store: str
    cut: int


def search_game(title: str, api_key: str) -> str | None:
    response = requests.get(
        f"{ITAD_BASE}/games/search/v1",
        params={"title": title, "key": api_key},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json()
    return results[0]["id"] if results else None


def get_best_price(itad_id: str, api_key: str) -> BestPrice | None:
    response = requests.post(
        f"{ITAD_BASE}/games/prices/v3",
        params={"key": api_key, "country": "US"},
        json=[itad_id],
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if not data:
        return None
    deals = data[0].get("deals", [])
    if not deals:
        return None
    best = min(deals, key=lambda d: d["price"]["amount"])
    return BestPrice(
        price=best["price"]["amount"],
        regular_price=best["regular"]["amount"],
        store=best["shop"]["name"],
        cut=best["cut"],
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_itad.py -v`
Expected: 5 passed

- [ ] **Step 5: Lint and format**

Run: `ruff check utils/itad.py tests/test_itad.py && ruff format utils/itad.py tests/test_itad.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add utils/itad.py tests/test_itad.py
git commit -m "feat: add IsThereAnyDeal API wrapper"
```

---

### Task 4: Discord Webhook Helper

**Files:**
- Create: `utils/discord.py`
- Create: `tests/test_discord.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_discord.py
from unittest.mock import MagicMock, patch

import pytest

from utils.discord import send_deal_alert


def test_send_deal_alert_posts_formatted_message():
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    with patch("utils.discord.requests.post", return_value=mock_resp) as mock_post:
        send_deal_alert(
            webhook_url="https://discord.com/api/webhooks/test/token",
            game_title="Elden Ring",
            store="Steam",
            price=29.99,
            regular_price=59.99,
            cut=50,
            ai_commentary="This is an all-time low — grab it now.",
        )
    mock_post.assert_called_once()
    payload = mock_post.call_args.kwargs["json"]
    assert "Elden Ring" in payload["content"]
    assert "Steam" in payload["content"]
    assert "29.99" in payload["content"]
    assert "50%" in payload["content"]
    assert "all-time low" in payload["content"]


def test_send_deal_alert_raises_on_http_error():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("HTTP 400")
    with patch("utils.discord.requests.post", return_value=mock_resp):
        with pytest.raises(Exception, match="HTTP 400"):
            send_deal_alert(
                webhook_url="https://discord.com/api/webhooks/test/token",
                game_title="Hades",
                store="GOG",
                price=4.99,
                regular_price=24.99,
                cut=80,
                ai_commentary="Great deal.",
            )
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_discord.py -v`
Expected: `ModuleNotFoundError: No module named 'utils.discord'`

- [ ] **Step 3: Implement `utils/discord.py`**

```python
# utils/discord.py
import requests


def send_deal_alert(
    webhook_url: str,
    game_title: str,
    store: str,
    price: float,
    regular_price: float,
    cut: int,
    ai_commentary: str,
) -> None:
    content = (
        f"**{game_title}** is {cut}% off on {store}!\n"
        f"**${price:.2f}** (was ${regular_price:.2f})\n"
        f"{ai_commentary}"
    )
    response = requests.post(webhook_url, json={"content": content}, timeout=10)
    response.raise_for_status()
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_discord.py -v`
Expected: 2 passed

- [ ] **Step 5: Lint and format**

Run: `ruff check utils/discord.py tests/test_discord.py && ruff format utils/discord.py tests/test_discord.py`

- [ ] **Step 6: Commit**

```bash
git add utils/discord.py tests/test_discord.py
git commit -m "feat: add Discord webhook helper"
```

---

### Task 5: AI Provider Abstraction

**Files:**
- Create: `ai/base.py`
- Create: `ai/groq_provider.py`
- Create: `ai/gemini_provider.py`
- Create: `ai/factory.py`
- Create: `tests/test_ai.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ai.py
from unittest.mock import MagicMock, patch

import pytest

from ai.base import AIProvider
from ai.factory import get_provider
from ai.gemini_provider import GeminiProvider
from ai.groq_provider import GroqProvider


def test_ai_provider_is_abstract():
    with pytest.raises(TypeError):
        AIProvider()


def test_groq_provider_returns_recommendation():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="  Great deal on Elden Ring!  "))
    ]
    provider = GroqProvider(client=mock_client)
    result = provider.recommend("Elden Ring", price=29.99, regular_price=59.99, store="Steam", cut=50)
    assert result == "Great deal on Elden Ring!"
    mock_client.chat.completions.create.assert_called_once()


def test_groq_provider_uses_correct_model():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="Buy it!"))
    ]
    provider = GroqProvider(client=mock_client)
    provider.recommend("Hades", price=4.99, regular_price=24.99, store="GOG", cut=80)
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "llama-3.3-70b-versatile"


def test_gemini_provider_returns_recommendation():
    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = "  This is a steal at $4.99.  "
    provider = GeminiProvider(model=mock_model)
    result = provider.recommend("Celeste", price=4.99, regular_price=19.99, store="Steam", cut=75)
    assert result == "This is a steal at $4.99."
    mock_model.generate_content.assert_called_once()


def test_factory_returns_groq_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "testkey")
    with patch("ai.factory.Groq") as mock_groq_cls:
        mock_groq_cls.return_value = MagicMock()
        provider = get_provider()
    assert isinstance(provider, GroqProvider)


def test_factory_returns_gemini_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "testkey")
    with patch("ai.factory.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value = MagicMock()
        provider = get_provider()
    assert isinstance(provider, GeminiProvider)


def test_factory_raises_on_unknown_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    with pytest.raises(ValueError, match="Unknown AI_PROVIDER: openai"):
        get_provider()
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_ai.py -v`
Expected: `ModuleNotFoundError: No module named 'ai.base'`

- [ ] **Step 3: Implement `ai/base.py`**

```python
# ai/base.py
from abc import ABC, abstractmethod


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
```

- [ ] **Step 4: Implement `ai/groq_provider.py`**

```python
# ai/groq_provider.py
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
```

- [ ] **Step 5: Implement `ai/gemini_provider.py`**

```python
# ai/gemini_provider.py
import google.generativeai as genai

from ai.base import AIProvider


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
```

- [ ] **Step 6: Implement `ai/factory.py`**

```python
# ai/factory.py
import os

import google.generativeai as genai
from groq import Groq

from ai.base import AIProvider
from ai.gemini_provider import GeminiProvider
from ai.groq_provider import GroqProvider


def get_provider() -> AIProvider:
    name = os.environ.get("AI_PROVIDER", "groq")
    if name == "groq":
        return GroqProvider(client=Groq(api_key=os.environ["GROQ_API_KEY"]))
    if name == "gemini":
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        return GeminiProvider(model=genai.GenerativeModel("gemini-1.5-flash"))
    raise ValueError(f"Unknown AI_PROVIDER: {name}")
```

- [ ] **Step 7: Run tests to confirm they pass**

Run: `pytest tests/test_ai.py -v`
Expected: 7 passed

- [ ] **Step 8: Lint and format**

Run: `ruff check ai/ tests/test_ai.py && ruff format ai/ tests/test_ai.py`
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add ai/ tests/test_ai.py
git commit -m "feat: add AI provider abstraction with Groq and Gemini implementations"
```

---

### Task 6: Cron Worker

**Files:**
- Create: `cron/price_check.py`
- Create: `tests/test_price_check.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_price_check.py
from unittest.mock import MagicMock, patch

import pytest

from cron.price_check import process_game, run


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_ai():
    ai = MagicMock()
    ai.recommend.return_value = "This is a great deal!"
    return ai


def test_process_game_sends_alert_when_at_historical_low(mock_db, mock_ai):
    game = {"id": "game-uuid", "title": "Elden Ring", "itad_id": "018d..."}
    best_price = MagicMock(price=14.99, regular_price=59.99, store="Steam", cut=75)

    with (
        patch("cron.price_check.insert_price_history"),
        patch("cron.price_check.get_historical_low", return_value=19.99),
        patch("cron.price_check.was_notified_recently", return_value=False),
        patch("cron.price_check.log_notification") as mock_log,
        patch("cron.price_check.send_deal_alert") as mock_alert,
    ):
        process_game(game, best_price, mock_db, mock_ai, webhook_url="https://hook.url")

    mock_alert.assert_called_once_with(
        webhook_url="https://hook.url",
        game_title="Elden Ring",
        store="Steam",
        price=14.99,
        regular_price=59.99,
        cut=75,
        ai_commentary="This is a great deal!",
    )
    mock_log.assert_called_once_with(mock_db, "game-uuid", 14.99)


def test_process_game_skips_when_above_historical_low(mock_db, mock_ai):
    game = {"id": "game-uuid", "title": "Elden Ring", "itad_id": "018d..."}
    best_price = MagicMock(price=39.99, regular_price=59.99, store="Steam", cut=33)

    with (
        patch("cron.price_check.insert_price_history"),
        patch("cron.price_check.get_historical_low", return_value=29.99),
        patch("cron.price_check.send_deal_alert") as mock_alert,
        patch("cron.price_check.log_notification") as mock_log,
    ):
        process_game(game, best_price, mock_db, mock_ai, webhook_url="https://hook.url")

    mock_alert.assert_not_called()
    mock_log.assert_not_called()


def test_process_game_skips_when_notified_recently(mock_db, mock_ai):
    game = {"id": "game-uuid", "title": "Elden Ring", "itad_id": "018d..."}
    best_price = MagicMock(price=9.99, regular_price=59.99, store="Steam", cut=83)

    with (
        patch("cron.price_check.insert_price_history"),
        patch("cron.price_check.get_historical_low", return_value=14.99),
        patch("cron.price_check.was_notified_recently", return_value=True),
        patch("cron.price_check.send_deal_alert") as mock_alert,
    ):
        process_game(game, best_price, mock_db, mock_ai, webhook_url="https://hook.url")

    mock_alert.assert_not_called()


def test_process_game_skips_when_no_price_available(mock_db, mock_ai):
    game = {"id": "game-uuid", "title": "Obscure Game", "itad_id": "obscure..."}

    with (
        patch("cron.price_check.insert_price_history") as mock_insert,
        patch("cron.price_check.send_deal_alert") as mock_alert,
    ):
        process_game(game, None, mock_db, mock_ai, webhook_url="https://hook.url")

    mock_insert.assert_not_called()
    mock_alert.assert_not_called()


def test_process_game_alerts_when_equal_to_historical_low(mock_db, mock_ai):
    game = {"id": "game-uuid", "title": "Hades", "itad_id": "hades..."}
    best_price = MagicMock(price=9.99, regular_price=24.99, store="GOG", cut=60)

    with (
        patch("cron.price_check.insert_price_history"),
        patch("cron.price_check.get_historical_low", return_value=9.99),
        patch("cron.price_check.was_notified_recently", return_value=False),
        patch("cron.price_check.log_notification"),
        patch("cron.price_check.send_deal_alert") as mock_alert,
    ):
        process_game(game, best_price, mock_db, mock_ai, webhook_url="https://hook.url")

    mock_alert.assert_called_once()


def test_run_calls_process_game_for_each_game(mock_db, mock_ai):
    games = [
        {"id": "g1", "title": "Elden Ring", "itad_id": "018d..."},
        {"id": "g2", "title": "Hades", "itad_id": "hades..."},
    ]
    best_price = MagicMock(price=9.99, regular_price=59.99, store="Steam", cut=83)

    with (
        patch("cron.price_check.get_games", return_value=games),
        patch("cron.price_check.get_best_price", return_value=best_price) as mock_get_price,
        patch("cron.price_check.process_game") as mock_process,
    ):
        run(db=mock_db, ai=mock_ai, itad_key="testkey", webhook_url="https://hook.url")

    assert mock_get_price.call_count == 2
    assert mock_process.call_count == 2
    mock_process.assert_any_call(
        games[0], best_price, mock_db, mock_ai, webhook_url="https://hook.url"
    )
    mock_process.assert_any_call(
        games[1], best_price, mock_db, mock_ai, webhook_url="https://hook.url"
    )
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_price_check.py -v`
Expected: `ModuleNotFoundError: No module named 'cron.price_check'`

- [ ] **Step 3: Implement `cron/price_check.py`**

```python
# cron/price_check.py
import os

from dotenv import load_dotenv

from ai.base import AIProvider
from ai.factory import get_provider
from db.client import (
    get_client,
    get_games,
    get_historical_low,
    insert_price_history,
    log_notification,
    was_notified_recently,
)
from utils.discord import send_deal_alert
from utils.itad import BestPrice, get_best_price


def process_game(
    game: dict,
    best_price: BestPrice | None,
    db,
    ai: AIProvider,
    webhook_url: str,
) -> None:
    if best_price is None:
        return

    insert_price_history(db, game["id"], best_price.price, best_price.regular_price, best_price.store)

    historical_low = get_historical_low(db, game["id"])
    if historical_low is None or best_price.price > historical_low:
        return

    if was_notified_recently(db, game["id"]):
        return

    commentary = ai.recommend(
        game_title=game["title"],
        price=best_price.price,
        regular_price=best_price.regular_price,
        store=best_price.store,
        cut=best_price.cut,
    )
    send_deal_alert(
        webhook_url=webhook_url,
        game_title=game["title"],
        store=best_price.store,
        price=best_price.price,
        regular_price=best_price.regular_price,
        cut=best_price.cut,
        ai_commentary=commentary,
    )
    log_notification(db, game["id"], best_price.price)


def run(db, ai: AIProvider, itad_key: str, webhook_url: str) -> None:
    games = get_games(db)
    for game in games:
        best_price = get_best_price(game["itad_id"], api_key=itad_key)
        process_game(game, best_price, db, ai, webhook_url=webhook_url)


if __name__ == "__main__":
    load_dotenv()
    db_client = get_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    ai_provider = get_provider()
    run(
        db=db_client,
        ai=ai_provider,
        itad_key=os.environ["ITAD_API_KEY"],
        webhook_url=os.environ["DISCORD_WEBHOOK_URL"],
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_price_check.py -v`
Expected: 6 passed

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All 26 tests pass (12 + 5 + 2 + 7 + 6 = 32 — adjust count based on actual results)

- [ ] **Step 6: Lint and format**

Run: `ruff check cron/ tests/test_price_check.py && ruff format cron/ tests/test_price_check.py`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add cron/price_check.py tests/test_price_check.py
git commit -m "feat: add cron worker — price check pipeline with deal detection"
```

---

### Task 7: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/price_check.yml`

- [ ] **Step 1: Create the workflow directory**

Run: `mkdir -p .github/workflows`

- [ ] **Step 2: Create `.github/workflows/price_check.yml`**

```yaml
name: Price Check

on:
  schedule:
    - cron: '0 */12 * * *'   # Every 12 hours at :00
  workflow_dispatch:           # Allow manual trigger from GitHub UI

jobs:
  price-check:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

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

- [ ] **Step 3: Verify the workflow file is valid YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/price_check.yml'))"`
Expected: No output (parses successfully)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/price_check.yml
git commit -m "feat: add GitHub Actions cron workflow for price check every 12h"
```

---

## GitHub Actions Secrets to Configure

After pushing to GitHub, add these secrets at **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase service role key |
| `ITAD_API_KEY` | Your IsThereAnyDeal API key |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL for #deals channel |
| `GROQ_API_KEY` | Your Groq API key (if using Groq) |
| `GEMINI_API_KEY` | Your Gemini API key (if using Gemini) |
| `AI_PROVIDER` | `groq` or `gemini` |

## Supabase Tables to Create

Run this SQL in the Supabase SQL editor to create the schema:

```sql
create extension if not exists "pgcrypto";

create table games (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  itad_id text not null unique,
  added_at timestamptz not null default now()
);

create table price_history (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  price numeric not null,
  regular_price numeric not null,
  store text not null,
  fetched_at timestamptz not null default now()
);

create table notifications_log (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  price numeric not null,
  notified_at timestamptz not null default now()
);

create index on price_history (game_id, price);
create index on notifications_log (game_id, notified_at desc);
```
