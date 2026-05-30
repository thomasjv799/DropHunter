# Watch Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users track watch prices from swisstimehouse.com by URL with a required target price, and fire a Discord alert when the price drops to/below target — running as a parallel path alongside the existing game tracker.

**Architecture:** A parallel "watch" path that mirrors the game path but swaps the price source. Watches are fetched with `cloudscraper` (swisstimehouse is behind Cloudflare) and parsed from the page's embedded `schema.org` JSON-LD. Three new DB tables (`watches`, `watch_price_history`, `watch_notifications_log`) leave the game tables untouched. The schema carries `myntra_*` columns reserved for a future source, but only swisstimehouse is implemented now.

**Tech Stack:** Python 3.11, Supabase (PostgreSQL), `cloudscraper` + `beautifulsoup4` (new), pytest + pytest-mock, LangGraph/Groq/Gemini (existing AI layer), Discord webhooks.

**Spec:** `docs/superpowers/specs/2026-05-30-watch-tracking-design.md`

---

## File Structure

**Create:**
- `utils/watches.py` — `fetch_swisstimehouse(url)`: cloudscraper fetch + JSON-LD parse. Single responsibility: turn a swisstimehouse URL into `{name, brand, reference, price}` or `None`.
- `tests/test_watches.py` — tests for `fetch_swisstimehouse` against a saved HTML fixture.
- `tests/fixtures/swisstimehouse_casio_g1714.html` — saved real product page HTML for deterministic parser tests.

**Modify:**
- `db/schema.sql` — add the three `watch*` tables.
- `db/client.py` — watch CRUD + price-history + notification helpers.
- `bot/functions.py` — `add_watch` / `list_watches` / `get_watch_price` / `set_watch_target` / `remove_watch`, registered in `TOOLS` and `_FUNCTION_MAP`.
- `utils/discord.py` — `send_watch_alert(...)`.
- `cron/price_check.py` — `process_watch(watch)` + watch loop in `run()`.
- `ai/graph.py` — extend `_SYSTEM_PROMPT` to mention watch tracking.
- `requirements.txt` — add `cloudscraper`, `beautifulsoup4`.

**Test files (modify/add):**
- `tests/test_watches.py`, `tests/test_db.py`, `tests/test_bot_functions.py`, `tests/test_cron.py`, `tests/test_discord_webhook.py`.

---

## Task 1: Add dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the two new dependencies**

Append these two lines to `requirements.txt` (after `tenacity==8.5.0`, keeping existing entries):

```
cloudscraper==1.2.71
beautifulsoup4==4.12.3
```

- [ ] **Step 2: Install them**

Run: `pip install cloudscraper==1.2.71 beautifulsoup4==4.12.3`
Expected: `Successfully installed ... cloudscraper-1.2.71 ... beautifulsoup4-4.12.3 ...`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "build: add cloudscraper and beautifulsoup4 for watch tracking"
```

---

## Task 2: Save a real swisstimehouse HTML fixture

A real fixture makes the parser test deterministic and offline. We save the live page once.

**Files:**
- Create: `tests/fixtures/swisstimehouse_casio_g1714.html`

- [ ] **Step 1: Download the live page via cloudscraper into the fixture**

Run:

```bash
mkdir -p tests/fixtures
python -c "import cloudscraper; open('tests/fixtures/swisstimehouse_casio_g1714.html','w').write(cloudscraper.create_scraper().get('https://www.swisstimehouse.com/casio-g1714', timeout=30).text)"
```

Expected: command exits 0 and the file is created.

- [ ] **Step 2: Verify the fixture contains the JSON-LD Product price**

Run: `grep -c '"@type": "Product"' tests/fixtures/swisstimehouse_casio_g1714.html`
Expected: a number `>= 1` (the page has at least one `Product` JSON-LD block).

Run: `grep -o '"price": *"\?34997' tests/fixtures/swisstimehouse_casio_g1714.html | head -1`
Expected: a match like `"price": 34997` or `"price": "34997"`.

> If the live price has changed since this plan was written, that is fine — note the **actual** integer price you see in the fixture and use it as the expected value in Task 3's test instead of `34997`.

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/swisstimehouse_casio_g1714.html
git commit -m "test: add swisstimehouse product page fixture"
```

---

## Task 3: `utils/watches.py` — fetch + parse

**Files:**
- Create: `utils/watches.py`
- Test: `tests/test_watches.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_watches.py`:

```python
# tests/test_watches.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "swisstimehouse_casio_g1714.html"


def _mock_scraper_returning(html: str):
    """Build a fake cloudscraper whose .get(...) returns a response with .text=html."""
    response = MagicMock()
    response.text = html
    response.status_code = 200
    response.raise_for_status.return_value = None
    scraper = MagicMock()
    scraper.get.return_value = response
    return scraper


def test_fetch_swisstimehouse_parses_jsonld():
    from utils.watches import fetch_swisstimehouse

    html = FIXTURE.read_text()
    with patch("utils.watches.cloudscraper.create_scraper", return_value=_mock_scraper_returning(html)):
        result = fetch_swisstimehouse("https://www.swisstimehouse.com/casio-g1714")

    assert result is not None
    assert result["brand"] == "Casio"
    assert result["reference"] == "G1714"
    assert "Casio" in result["name"]
    assert result["price"] == 34997.0
    assert isinstance(result["price"], float)


def test_fetch_swisstimehouse_rejects_non_swisstimehouse_url():
    from utils.watches import fetch_swisstimehouse

    result = fetch_swisstimehouse("https://www.amazon.in/some-watch")
    assert result is None


def test_fetch_swisstimehouse_returns_none_when_no_product_jsonld():
    from utils.watches import fetch_swisstimehouse

    html = "<html><head><title>nope</title></head><body>no structured data</body></html>"
    with patch("utils.watches.cloudscraper.create_scraper", return_value=_mock_scraper_returning(html)):
        result = fetch_swisstimehouse("https://www.swisstimehouse.com/casio-g1714")
    assert result is None


def test_fetch_swisstimehouse_returns_none_on_request_error():
    from utils.watches import fetch_swisstimehouse

    scraper = MagicMock()
    scraper.get.side_effect = Exception("Cloudflare blocked")
    with patch("utils.watches.cloudscraper.create_scraper", return_value=scraper):
        result = fetch_swisstimehouse("https://www.swisstimehouse.com/casio-g1714")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_watches.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.watches'`.

- [ ] **Step 3: Implement `utils/watches.py`**

Create `utils/watches.py`:

```python
import json
import logging
from urllib.parse import urlparse

import cloudscraper
from bs4 import BeautifulSoup

logger = logging.getLogger("drophunter.watches")

_ALLOWED_HOST = "swisstimehouse.com"


def _is_swisstimehouse(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == _ALLOWED_HOST or host.endswith("." + _ALLOWED_HOST)


def _extract_product_jsonld(html: str) -> dict | None:
    """Return the first schema.org Product JSON-LD object with a price, or None."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") != "Product":
                continue
            offers = obj.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if offers.get("price") is None:
                continue
            return obj
    return None


def fetch_swisstimehouse(url: str) -> dict | None:
    """
    Fetch a swisstimehouse.com product page and parse its schema.org JSON-LD.
    Returns {name, brand, reference, price} or None on any failure.
    """
    if not _is_swisstimehouse(url):
        logger.warning("Rejecting non-swisstimehouse URL: %s", url)
        return None

    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=30)
        response.raise_for_status()
        html = response.text
    except Exception as exc:
        logger.warning("Failed to fetch swisstimehouse URL %s: %s", url, exc)
        return None

    product = _extract_product_jsonld(html)
    if product is None:
        logger.warning("No Product JSON-LD with a price found at %s", url)
        return None

    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    brand = product.get("brand") or {}
    brand_name = brand.get("name") if isinstance(brand, dict) else brand

    result = {
        "name": product.get("name"),
        "brand": brand_name,
        "reference": product.get("sku") or product.get("mpn"),
        "price": float(offers["price"]),
    }
    logger.info(
        "Fetched %s: %s (ref=%s) ₹%.2f",
        url, result["name"], result["reference"], result["price"],
    )
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_watches.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint**

Run: `ruff check utils/watches.py tests/test_watches.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add utils/watches.py tests/test_watches.py
git commit -m "feat: add fetch_swisstimehouse with cloudscraper + JSON-LD parsing"
```

---

## Task 4: Database schema — watch tables

**Files:**
- Modify: `db/schema.sql`

- [ ] **Step 1: Append the watch tables to `db/schema.sql`**

Add at the end of `db/schema.sql`:

```sql
create table if not exists watches (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    brand text null,
    reference_no text null,
    target_price numeric not null,
    swisstimehouse_url text null unique,
    myntra_url text null,
    added_at timestamptz not null default now()
);

create table if not exists watch_price_history (
    id uuid primary key default gen_random_uuid(),
    watch_id uuid not null references watches(id) on delete cascade,
    swisstimehouse_price numeric null,
    myntra_price numeric null,
    fetched_at timestamptz not null default now()
);

create table if not exists watch_notifications_log (
    id uuid primary key default gen_random_uuid(),
    watch_id uuid not null references watches(id) on delete cascade,
    price numeric not null,
    seller text not null,
    notified_at timestamptz not null default now()
);

create index if not exists idx_watch_price_history_watch_id on watch_price_history(watch_id);
create index if not exists idx_watch_notifications_log_watch_id on watch_notifications_log(watch_id);
```

- [ ] **Step 2: Apply the schema to Supabase**

Run this SQL in the Supabase SQL editor (or via the project's existing migration path). This is a manual/operational step — `db/schema.sql` is the source of truth for the tables; there is no automated migration runner in this repo.
Expected: three tables created, no errors. Verify with: `select count(*) from watches;` → returns `0`.

- [ ] **Step 3: Commit**

```bash
git add db/schema.sql
git commit -m "feat: add watches, watch_price_history, watch_notifications_log tables"
```

---

## Task 5: DB client — watch CRUD helpers

**Files:**
- Modify: `db/client.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_db.py`:

```python
def test_add_watch_upserts(mocker):
    from db import client

    fake_table = mocker.MagicMock()
    fake_table.upsert.return_value.execute.return_value.data = [{"id": "w1", "name": "Casio G1714"}]
    mocker.patch.object(client, "_get_client", return_value=mocker.MagicMock(table=lambda *_: fake_table))

    result = client.add_watch(
        name="Casio G1714", brand="Casio", reference_no="G1714",
        target_price=30000.0, swisstimehouse_url="https://www.swisstimehouse.com/casio-g1714",
    )
    assert result["id"] == "w1"
    fake_table.upsert.assert_called_once()
    args, kwargs = fake_table.upsert.call_args
    assert kwargs.get("on_conflict") == "swisstimehouse_url"
    assert args[0]["target_price"] == 30000.0


def test_get_watches_returns_rows(mocker):
    from db import client

    fake_table = mocker.MagicMock()
    fake_table.select.return_value.execute.return_value.data = [{"id": "w1", "name": "Casio G1714"}]
    mocker.patch.object(client, "_get_client", return_value=mocker.MagicMock(table=lambda *_: fake_table))

    rows = client.get_watches()
    assert rows == [{"id": "w1", "name": "Casio G1714"}]


def test_set_watch_target_updates_match(mocker):
    from db import client

    mocker.patch.object(client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}])
    fake_table = mocker.MagicMock()
    fake_table.update.return_value.eq.return_value.execute.return_value.data = [{"id": "w1"}]
    mocker.patch.object(client, "_get_client", return_value=mocker.MagicMock(table=lambda *_: fake_table))

    assert client.set_watch_target("casio g1714", 25000.0) is True


def test_set_watch_target_no_match(mocker):
    from db import client

    mocker.patch.object(client, "get_watches", return_value=[])
    assert client.set_watch_target("nonexistent", 25000.0) is False


def test_remove_watch_deletes_match(mocker):
    from db import client

    mocker.patch.object(client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}])
    fake_table = mocker.MagicMock()
    fake_table.delete.return_value.eq.return_value.execute.return_value.data = [{"id": "w1"}]
    mocker.patch.object(client, "_get_client", return_value=mocker.MagicMock(table=lambda *_: fake_table))

    assert client.remove_watch("Casio G1714") is True


def test_get_last_watch_notified_price(mocker):
    from db import client

    fake_table = mocker.MagicMock()
    chain = fake_table.select.return_value.eq.return_value.order.return_value.limit.return_value
    chain.execute.return_value.data = [{"price": 28000}]
    mocker.patch.object(client, "_get_client", return_value=mocker.MagicMock(table=lambda *_: fake_table))

    assert client.get_last_watch_notified_price("w1") == 28000.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -k watch -v`
Expected: FAIL — `AttributeError: module 'db.client' has no attribute 'add_watch'` (and similar).

- [ ] **Step 3: Implement the helpers in `db/client.py`**

Append to `db/client.py`:

```python
def get_watches() -> list:
    logger.debug("Fetching all watches")
    return _get_client().table("watches").select("*").execute().data


def add_watch(
    name: str,
    brand: Optional[str],
    reference_no: Optional[str],
    target_price: float,
    swisstimehouse_url: str,
) -> dict:
    logger.info("Adding watch: %s (target=%s, url=%s)", name, target_price, swisstimehouse_url)
    row = {
        "name": name,
        "brand": brand,
        "reference_no": reference_no,
        "target_price": target_price,
        "swisstimehouse_url": swisstimehouse_url,
    }
    result = (
        _get_client().table("watches").upsert(row, on_conflict="swisstimehouse_url").execute()
    )
    if not result.data:
        raise RuntimeError(f"Insert into 'watches' returned no data: {result}")
    return result.data[0]


def _find_watch_by_name(name: str) -> Optional[dict]:
    """Fuzzy-match a watch by name, reusing the same normalization as games."""
    norm_query = _normalize(name)
    watches = get_watches()
    for w in watches:
        if _normalize(w["name"]) == norm_query:
            return w
    for w in watches:
        if norm_query in _normalize(w["name"]) or _normalize(w["name"]) in norm_query:
            return w
    return None


def set_watch_target(name: str, target_price: float) -> bool:
    watch = _find_watch_by_name(name)
    if not watch:
        logger.warning("No watch matched '%s' for target update", name)
        return False
    result = (
        _get_client().table("watches").update({"target_price": target_price}).eq("id", watch["id"]).execute()
    )
    return len(result.data) > 0


def remove_watch(name: str) -> bool:
    watch = _find_watch_by_name(name)
    if not watch:
        logger.warning("No watch matched '%s' for removal", name)
        return False
    result = _get_client().table("watches").delete().eq("id", watch["id"]).execute()
    return len(result.data) > 0


def insert_watch_price_history(
    watch_id: str,
    swisstimehouse_price: Optional[float],
    myntra_price: Optional[float] = None,
) -> dict:
    result = (
        _get_client()
        .table("watch_price_history")
        .insert(
            {
                "watch_id": watch_id,
                "swisstimehouse_price": swisstimehouse_price,
                "myntra_price": myntra_price,
            }
        )
        .execute()
    )
    if not result.data:
        raise RuntimeError(f"Insert into 'watch_price_history' returned no data: {result}")
    return result.data[0]


def get_last_watch_notified_price(watch_id: str) -> Optional[float]:
    result = (
        _get_client()
        .table("watch_notifications_log")
        .select("price")
        .eq("watch_id", watch_id)
        .order("notified_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return float(result.data[0]["price"])


def log_watch_notification(watch_id: str, price: float, seller: str) -> dict:
    logger.info("Logging watch notification: watch_id=%s price=%.2f seller=%s", watch_id, price, seller)
    result = (
        _get_client()
        .table("watch_notifications_log")
        .insert({"watch_id": watch_id, "price": price, "seller": seller})
        .execute()
    )
    if not result.data:
        raise RuntimeError(f"Insert into 'watch_notifications_log' returned no data: {result}")
    return result.data[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -k watch -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Lint and commit**

Run: `ruff check db/client.py tests/test_db.py`
Expected: no errors.

```bash
git add db/client.py tests/test_db.py
git commit -m "feat: add watch CRUD and price-history db helpers"
```

---

## Task 6: Bot tools — add/list/get/set/remove watch

**Files:**
- Modify: `bot/functions.py`
- Test: `tests/test_bot_functions.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bot_functions.py`:

```python
def test_add_watch_asks_for_target_when_missing(mocker):
    from bot.functions import add_watch

    mocker.patch(
        "bot.functions.fetch_swisstimehouse",
        return_value={"name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 34997.0},
    )
    mock_db = mocker.patch("bot.functions.db_add_watch")
    result = add_watch("https://www.swisstimehouse.com/casio-g1714")
    assert "34997" in result
    assert "target" in result.lower()
    mock_db.assert_not_called()


def test_add_watch_stores_with_target(mocker):
    from bot.functions import add_watch

    mocker.patch(
        "bot.functions.fetch_swisstimehouse",
        return_value={"name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 34997.0},
    )
    mock_db = mocker.patch("bot.functions.db_add_watch", return_value={"id": "w1", "name": "Casio G1714"})
    result = add_watch("https://www.swisstimehouse.com/casio-g1714", target_price=30000.0)
    assert "Casio G1714" in result
    assert "30000" in result
    mock_db.assert_called_once_with(
        name="Casio G1714", brand="Casio", reference_no="G1714",
        target_price=30000.0, swisstimehouse_url="https://www.swisstimehouse.com/casio-g1714",
    )


def test_add_watch_fetch_failure(mocker):
    from bot.functions import add_watch

    mocker.patch("bot.functions.fetch_swisstimehouse", return_value=None)
    result = add_watch("https://www.swisstimehouse.com/bad", target_price=30000.0)
    assert "couldn't" in result.lower() or "could not" in result.lower() or "unable" in result.lower()


def test_list_watches_with_rows(mocker):
    from bot.functions import list_watches

    mocker.patch(
        "bot.functions.db_get_watches",
        return_value=[{"name": "Casio G1714", "target_price": 30000.0}],
    )
    result = list_watches()
    assert "Casio G1714" in result
    assert "30000" in result


def test_list_watches_empty(mocker):
    from bot.functions import list_watches

    mocker.patch("bot.functions.db_get_watches", return_value=[])
    result = list_watches()
    assert "empty" in result.lower() or "no watches" in result.lower()


def test_set_watch_target_success(mocker):
    from bot.functions import set_watch_target

    mocker.patch("bot.functions.db_set_watch_target", return_value=True)
    result = set_watch_target("Casio G1714", 25000.0)
    assert "25000" in result


def test_remove_watch_success(mocker):
    from bot.functions import remove_watch

    mocker.patch("bot.functions.db_remove_watch", return_value=True)
    result = remove_watch("Casio G1714")
    assert "no longer" in result.lower() or "removed" in result.lower()


def test_dispatch_routes_to_add_watch(mocker):
    from bot.functions import dispatch

    mocker.patch(
        "bot.functions.fetch_swisstimehouse",
        return_value={"name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 34997.0},
    )
    mocker.patch("bot.functions.db_add_watch", return_value={"id": "w1", "name": "Casio G1714"})
    result = dispatch("add_watch", {"url": "https://www.swisstimehouse.com/casio-g1714", "target_price": 30000.0})
    assert "Casio G1714" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot_functions.py -k watch -v`
Expected: FAIL — `ImportError: cannot import name 'add_watch'`.

- [ ] **Step 3: Implement the watch tools in `bot/functions.py`**

Add to the imports block at the top of `bot/functions.py` (extend the existing `from db.client import (...)` and `from utils...` lines):

```python
from db.client import (
    add_watch as db_add_watch,
    get_watches as db_get_watches,
    remove_watch as db_remove_watch,
    set_watch_target as db_set_watch_target,
)
from utils.watches import fetch_swisstimehouse
```

Add these functions (anywhere among the other tool functions, before `TOOLS`):

```python
def add_watch(url: str, target_price: float = None) -> str:
    logger.info("add_watch called: url=%s, target_price=%s", url, target_price)
    watch = fetch_swisstimehouse(url)
    if watch is None:
        return (
            f"Sorry, I couldn't read a price from that link. "
            f"Make sure it's a swisstimehouse.com product page."
        )
    if target_price is None:
        return (
            f"**{watch['name']}** is currently ₹{watch['price']:.2f} on Swiss Time House. "
            f"What target price (in ₹) should I alert you below?"
        )
    db_add_watch(
        name=watch["name"],
        brand=watch["brand"],
        reference_no=watch["reference"],
        target_price=target_price,
        swisstimehouse_url=url,
    )
    return (
        f"Tracking **{watch['name']}** (currently ₹{watch['price']:.2f}). "
        f"I'll alert you when it drops below ₹{target_price:.2f}."
    )


def list_watches() -> str:
    logger.info("list_watches called")
    watches = db_get_watches()
    if not watches:
        return "Your watch list is empty. Add one with a swisstimehouse.com product link."
    lines = ["**Watches you're tracking:**"]
    for w in watches:
        line = f"• {w['name']}"
        if w.get("target_price") is not None:
            line += f" (target: ₹{float(w['target_price']):.2f})"
        lines.append(line)
    return "\n".join(lines)


def get_watch_price(name: str) -> str:
    logger.info("get_watch_price called: name=%s", name)
    watches = db_get_watches()
    from db.client import _normalize
    norm = _normalize(name)
    match = next(
        (w for w in watches if norm in _normalize(w["name"]) or _normalize(w["name"]) in norm),
        None,
    )
    if not match or not match.get("swisstimehouse_url"):
        return f"**{name}** isn't on your watch list."
    fetched = fetch_swisstimehouse(match["swisstimehouse_url"])
    if fetched is None:
        return f"I couldn't fetch the current price for **{match['name']}** right now."
    return f"**{match['name']}** is currently ₹{fetched['price']:.2f} on Swiss Time House."


def set_watch_target(name: str, target_price: float) -> str:
    logger.info("set_watch_target called: name=%s, target_price=%s", name, target_price)
    updated = db_set_watch_target(name, target_price)
    if not updated:
        return f"**{name}** wasn't found in your watch list."
    return f"Target price for **{name}** set to ₹{target_price:.2f}."


def remove_watch(name: str) -> str:
    logger.info("remove_watch called: name=%s", name)
    removed = db_remove_watch(name)
    if removed:
        return f"No longer tracking **{name}**."
    return f"**{name}** wasn't in your watch list."
```

Add these tool definitions to the `TOOLS` list (append inside the list):

```python
    {
        "type": "function",
        "function": {
            "name": "add_watch",
            "description": (
                "Track a watch's price from a swisstimehouse.com product URL. "
                "Provide a target price in INR; the user is alerted when the price drops below it. "
                "If no target price is given, this returns the current price and asks for one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "A swisstimehouse.com product page URL."},
                    "target_price": {
                        "type": "number",
                        "description": "Target price in INR. Alert fires when price drops to/below this.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_watches",
            "description": "List all watches currently being tracked.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_watch_price",
            "description": "Get the current price of a tracked watch from swisstimehouse.com.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The name of the tracked watch."}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_watch_target",
            "description": "Set or update the target price (INR) for a tracked watch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The name of the tracked watch."},
                    "target_price": {"type": "number", "description": "New target price in INR."},
                },
                "required": ["name", "target_price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_watch",
            "description": "Remove a watch from the watch list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The name of the watch to remove."}
                },
                "required": ["name"],
            },
        },
    },
```

Add these entries to `_FUNCTION_MAP`:

```python
    "add_watch": add_watch,
    "list_watches": list_watches,
    "get_watch_price": get_watch_price,
    "set_watch_target": set_watch_target,
    "remove_watch": remove_watch,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bot_functions.py -k watch -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Lint and commit**

Run: `ruff check bot/functions.py tests/test_bot_functions.py`
Expected: no errors.

```bash
git add bot/functions.py tests/test_bot_functions.py
git commit -m "feat: add watch tools (add/list/get/set/remove) to bot"
```

---

## Task 7: Discord watch alert

**Files:**
- Modify: `utils/discord.py`
- Test: `tests/test_discord_webhook.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_discord_webhook.py`:

```python
def test_send_watch_alert_posts_message(mocker, monkeypatch):
    from utils import discord

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    mock_post = mocker.patch("utils.discord.requests.post")
    mock_post.return_value.raise_for_status.return_value = None

    discord.send_watch_alert(
        watch_name="Casio G1714",
        price=29000.0,
        seller="Swiss Time House",
        target_price=30000.0,
        ai_commentary="Great time to buy.",
    )

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    body = kwargs["json"]["content"]
    assert "Casio G1714" in body
    assert "29000" in body
    assert "Swiss Time House" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discord_webhook.py::test_send_watch_alert_posts_message -v`
Expected: FAIL — `AttributeError: module 'utils.discord' has no attribute 'send_watch_alert'`.

- [ ] **Step 3: Implement `send_watch_alert` in `utils/discord.py`**

Append to `utils/discord.py`:

```python
def send_watch_alert(
    watch_name: str,
    price: float,
    seller: str,
    target_price: float,
    ai_commentary: str,
) -> None:
    load_dotenv()
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise EnvironmentError("DISCORD_WEBHOOK_URL is not set. Add it to your .env file.")
    message = (
        f"**Watch Deal Alert: {watch_name}**\n"
        f"₹{price:.2f} on {seller} (target was ₹{target_price:.2f})\n"
        f"{ai_commentary}"
    )
    response = requests.post(webhook_url, json={"content": message})
    response.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_discord_webhook.py::test_send_watch_alert_posts_message -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

Run: `ruff check utils/discord.py tests/test_discord_webhook.py`
Expected: no errors.

```bash
git add utils/discord.py tests/test_discord_webhook.py
git commit -m "feat: add send_watch_alert discord helper"
```

---

## Task 8: Cron — `process_watch` and watch sweep

**Files:**
- Modify: `cron/price_check.py`
- Test: `tests/test_cron.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cron.py`:

```python
@pytest.fixture
def sample_watch():
    return {
        "id": "watch-uuid-1",
        "name": "Casio G1714",
        "target_price": 30000.0,
        "swisstimehouse_url": "https://www.swisstimehouse.com/casio-g1714",
        "myntra_url": None,
    }


def test_process_watch_sends_alert_below_target(sample_watch, mocker):
    from cron.price_check import process_watch

    mocker.patch(
        "cron.price_check.fetch_swisstimehouse",
        return_value={"name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 29000.0},
    )
    mock_hist = mocker.patch("cron.price_check.insert_watch_price_history")
    mocker.patch("cron.price_check.get_last_watch_notified_price", return_value=None)
    mock_provider = MagicMock()
    mock_provider.generate_text.return_value = "Buy now!"
    mocker.patch("cron.price_check.get_provider", return_value=mock_provider)
    mock_alert = mocker.patch("cron.price_check.send_watch_alert")
    mock_log = mocker.patch("cron.price_check.log_watch_notification")

    process_watch(sample_watch)

    mock_hist.assert_called_once_with(
        watch_id="watch-uuid-1", swisstimehouse_price=29000.0, myntra_price=None
    )
    mock_alert.assert_called_once()
    _, kwargs = mock_alert.call_args
    assert kwargs["watch_name"] == "Casio G1714"
    assert kwargs["price"] == 29000.0
    assert kwargs["seller"] == "Swiss Time House"
    mock_log.assert_called_once_with("watch-uuid-1", 29000.0, "Swiss Time House")


def test_process_watch_skips_above_target(sample_watch, mocker):
    from cron.price_check import process_watch

    mocker.patch(
        "cron.price_check.fetch_swisstimehouse",
        return_value={"name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 34997.0},
    )
    mocker.patch("cron.price_check.insert_watch_price_history")
    mock_alert = mocker.patch("cron.price_check.send_watch_alert")

    process_watch(sample_watch)
    mock_alert.assert_not_called()


def test_process_watch_skips_when_not_lower_than_last_notified(sample_watch, mocker):
    from cron.price_check import process_watch

    mocker.patch(
        "cron.price_check.fetch_swisstimehouse",
        return_value={"name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 29000.0},
    )
    mocker.patch("cron.price_check.insert_watch_price_history")
    mocker.patch("cron.price_check.get_last_watch_notified_price", return_value=29000.0)
    mock_alert = mocker.patch("cron.price_check.send_watch_alert")

    process_watch(sample_watch)
    mock_alert.assert_not_called()


def test_process_watch_skips_when_no_price(sample_watch, mocker):
    from cron.price_check import process_watch

    mocker.patch("cron.price_check.fetch_swisstimehouse", return_value=None)
    mock_hist = mocker.patch("cron.price_check.insert_watch_price_history")
    mock_alert = mocker.patch("cron.price_check.send_watch_alert")

    process_watch(sample_watch)
    mock_hist.assert_called_once_with(
        watch_id="watch-uuid-1", swisstimehouse_price=None, myntra_price=None
    )
    mock_alert.assert_not_called()


def test_run_checks_watches_too(mocker):
    from cron.price_check import run

    mocker.patch("cron.price_check.get_games", return_value=[])
    mocker.patch(
        "cron.price_check.get_watches",
        return_value=[{"id": "w1", "name": "Casio G1714"}],
    )
    mock_process_watch = mocker.patch("cron.price_check.process_watch")

    run()
    mock_process_watch.assert_called_once_with({"id": "w1", "name": "Casio G1714"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cron.py -k watch -v`
Expected: FAIL — `ImportError: cannot import name 'process_watch'`.

- [ ] **Step 3: Implement `process_watch` and extend `run()`**

In `cron/price_check.py`, extend the imports:

```python
from db.client import (
    get_games,
    get_last_notified_price,
    get_last_watch_notified_price,
    get_watches,
    insert_price_history,
    insert_watch_price_history,
    log_notification,
    log_watch_notification,
)
from utils.discord import send_deal_alert, send_watch_alert
from utils.itad import get_best_price, get_historical_low
from utils.watches import fetch_swisstimehouse
```

(Adjust the existing `from db.client import (...)` and `from utils.discord import ...` lines to the above — keep `get_provider` import as-is.)

Add the `process_watch` function:

```python
_SWISS_SELLER = "Swiss Time House"


def process_watch(watch: dict) -> None:
    name = watch["name"]
    logger.info("[%s] Fetching watch price...", name)

    swiss_price = None
    url = watch.get("swisstimehouse_url")
    if url:
        fetched = fetch_swisstimehouse(url)
        if fetched is not None:
            swiss_price = fetched["price"]

    insert_watch_price_history(
        watch_id=watch["id"], swisstimehouse_price=swiss_price, myntra_price=None
    )

    # Lowest available price across sources (only swisstimehouse in v1).
    candidates = [(swiss_price, _SWISS_SELLER)]
    available = [(p, s) for p, s in candidates if p is not None]
    if not available:
        logger.info("[%s] No price available this sweep, skipping.", name)
        return

    price, seller = min(available, key=lambda ps: ps[0])
    target = float(watch["target_price"])
    if price > target:
        logger.info("[%s] ₹%.2f above target ₹%.2f, skipping.", name, price, target)
        return

    last_notified = get_last_watch_notified_price(watch["id"])
    if last_notified is not None and price >= last_notified:
        logger.info(
            "[%s] ₹%.2f not lower than last notified ₹%.2f, skipping.",
            name, price, last_notified,
        )
        return

    logger.info("[%s] Deal! ₹%.2f on %s. Generating commentary...", name, price, seller)
    provider = get_provider()
    commentary = provider.generate_text(
        f"Write a one-sentence buy recommendation for the watch '{name}'. "
        f"Current price: ₹{price} on {seller}, below the user's target of ₹{target}."
    )
    send_watch_alert(
        watch_name=name,
        price=price,
        seller=seller,
        target_price=target,
        ai_commentary=commentary,
    )
    log_watch_notification(watch["id"], price, seller)
    logger.info("[%s] Watch alert sent!", name)
```

Extend `run()` — after the existing game loop and before the final log line, add:

```python
    watches = get_watches()
    logger.info("Checking prices for %d watch(es)...", len(watches))
    for watch in watches:
        try:
            process_watch(watch)
        except Exception as exc:
            logger.error("[%s] ERROR: %s", watch["name"], exc, exc_info=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cron.py -k watch -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full cron test file to confirm no regressions**

Run: `pytest tests/test_cron.py -v`
Expected: all PASS (existing game tests + new watch tests).

- [ ] **Step 6: Lint and commit**

Run: `ruff check cron/price_check.py tests/test_cron.py`
Expected: no errors.

```bash
git add cron/price_check.py tests/test_cron.py
git commit -m "feat: add process_watch and watch sweep to cron"
```

---

## Task 9: Extend the agent system prompt

**Files:**
- Modify: `ai/graph.py:26-32`

- [ ] **Step 1: Update `_SYSTEM_PROMPT`**

Replace the existing `_SYSTEM_PROMPT` assignment in `ai/graph.py` with:

```python
_SYSTEM_PROMPT = (
    "You are DropHunter, a personal deal assistant for games and watches. "
    "For games: when the user asks to track, untrack, list games, check prices, see recent deals, "
    "check historical lows, or set target prices, use the available tools. "
    "For watches: the user tracks a watch by giving a swisstimehouse.com product URL. "
    "Use add_watch with the URL; a target price in INR is required, so if the user hasn't given one, "
    "add_watch will report the current price and you should ask them for a target. "
    "Use list_watches, get_watch_price, set_watch_target, and remove_watch for watch management. "
    "You can call multiple tools in sequence if needed. "
    "For anything else, respond helpfully in plain text."
)
```

- [ ] **Step 2: Run the graph tests to confirm nothing broke**

Run: `pytest tests/test_graph.py -v`
Expected: all PASS.

- [ ] **Step 3: Lint and commit**

Run: `ruff check ai/graph.py`
Expected: no errors.

```bash
git add ai/graph.py
git commit -m "feat: teach agent about watch tracking"
```

---

## Task 10: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -v`
Expected: all tests PASS (existing + new). If any existing test fails, fix the regression before proceeding.

- [ ] **Step 2: Lint the whole project**

Run: `ruff check .`
Expected: no errors.

- [ ] **Step 3: Manual smoke test of the live fetch (optional but recommended)**

Run:

```bash
python -c "from utils.watches import fetch_swisstimehouse; print(fetch_swisstimehouse('https://www.swisstimehouse.com/casio-g1714'))"
```

Expected: a dict like `{'name': 'Casio G1714 - ...', 'brand': 'Casio', 'reference': 'G1714', 'price': 34997.0}` (price may differ if it changed). If it prints `None`, Cloudflare may have escalated its challenge — note this; the cron path already degrades gracefully (records `None`, sends no false alert).

- [ ] **Step 4: Final commit (if any lint fixes were made)**

```bash
git add -A
git commit -m "chore: watch tracking final verification fixes"
```

---

## Self-Review Notes (spec coverage)

- swisstimehouse fetch + JSON-LD parse → Task 3 ✓
- 3 watch tables (myntra columns reserved, NULL in v1) → Task 4 ✓
- DB helpers (CRUD, history, notifications, dedup) → Task 5 ✓
- Tools (add/list/get/set/remove) + required target + "ask for target" flow + upsert → Task 6 ✓
- Discord watch alert → Task 7 ✓
- `process_watch` with lowest-available-price + target + dedup + graceful None → Task 8 ✓
- Agent system prompt → Task 9 ✓
- `cloudscraper` + `beautifulsoup4` deps → Task 1 ✓
- Myntra deferred (schema present, no scraper) → reflected throughout ✓
