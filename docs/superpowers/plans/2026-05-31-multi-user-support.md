# Multi-User Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an owner permit specific Discord users to use DropHunter privately over DM, with each person's watchlist, history, and deal alerts isolated, and alerts delivered as per-user DMs.

**Architecture:** Three phases. **Phase 1 (Authorization):** an `allowed_users` table + `OWNER_ID` env bootstrap gate the bot to permitted users; DM-only. **Phase 2 (Isolation):** add a `user_id` owner column to `games`/`watches`, scope every watchlist query by it, and inject the current `user_id` into tool calls (never via the LLM). **Phase 3 (DM delivery):** the cron DMs each owner via the bot token + Discord REST instead of a shared webhook.

**Tech Stack:** Python 3.11/3.12, discord.py, Supabase (PostgreSQL), Groq/Gemini via LangGraph, pytest + pytest-mock.

**Spec:** `docs/superpowers/specs/2026-05-31-multi-user-design.md`

---

## File Structure

- `db/schema.sql` (modify) — `allowed_users` table; `user_id` on `games`/`watches`; composite uniqueness.
- `db/client.py` (modify) — allowlist helpers (`_owner_id`, `is_user_allowed`, `add_allowed_user`, `remove_allowed_user`, `list_allowed_users`); thread `user_id` through every watchlist helper.
- `bot/functions.py` (modify) — every tool function takes `user_id` first; `dispatch(name, args, user_id)`; drop `user_id` from the `clear_memory` schema.
- `ai/graph.py` (modify) — inject `state["user_id"]` into `dispatch`.
- `bot/client.py` (modify) — DM-only auth gate; owner-only `/allow` `/revoke` `/listusers`.
- `utils/discord.py` (modify) — `send_dm(user_id, message)` via bot token + REST.
- `cron/price_check.py` (modify) — DM the owner per row; skip revoked owners; sweep over all users.
- Tests across `tests/test_db.py`, `tests/test_bot_functions.py`, `tests/test_graph.py`, `tests/test_discord_webhook.py`, `tests/test_cron.py`.

Use `python3` to run anything (the `python` command is unavailable on the dev box). Runtime is py3.12.

---

# PHASE 1 — Authorization

## Task 1: `allowed_users` table + allowlist DB helpers

**Files:**
- Modify: `db/schema.sql`
- Modify: `db/client.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Add the table to `db/schema.sql`**

Append to `db/schema.sql`:

```sql
create table if not exists allowed_users (
    user_id text primary key,
    added_by text null,
    added_at timestamptz not null default now()
);
```

- [ ] **Step 2: Write the failing tests** — append to `tests/test_db.py`:

```python
def test_is_user_allowed_owner(monkeypatch):
    from db import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    assert client.is_user_allowed("owner123") is True


def test_is_user_allowed_allowlisted(monkeypatch, mocker):
    from db import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.eq.return_value.execute.return_value.data = [{"user_id": "u2"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.is_user_allowed("u2") is True


def test_is_user_allowed_stranger(monkeypatch, mocker):
    from db import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.eq.return_value.execute.return_value.data = []
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.is_user_allowed("stranger") is False


def test_add_allowed_user(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.upsert.return_value.execute.return_value.data = [
        {"user_id": "u2", "added_by": "owner123"}
    ]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.add_allowed_user("u2", "owner123")["user_id"] == "u2"


def test_remove_allowed_user(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.delete.return_value.eq.return_value.execute.return_value.data = [{"user_id": "u2"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.remove_allowed_user("u2") is True


def test_list_allowed_users(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.execute.return_value.data = [{"user_id": "u2"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.list_allowed_users() == [{"user_id": "u2"}]
```

- [ ] **Step 3: Run to verify failure**

Run: `cd /Users/thomasjvarghese/Repos/DropHunter && python3 -m pytest tests/test_db.py -k "allowed or is_user" -v`
Expected: FAIL — `AttributeError: module 'db.client' has no attribute 'is_user_allowed'`.

- [ ] **Step 4: Implement in `db/client.py`** (append; `os` and `load_dotenv` are already imported):

```python
def _owner_id() -> Optional[str]:
    load_dotenv()
    return os.environ.get("OWNER_ID")


def is_user_allowed(user_id: str) -> bool:
    """True if the user is the owner (env) or present in allowed_users."""
    if user_id == _owner_id():
        return True
    result = (
        _get_client().table("allowed_users").select("user_id").eq("user_id", user_id).execute()
    )
    return len(result.data) > 0


def add_allowed_user(user_id: str, added_by: str) -> dict:
    logger.info("Allowing user %s (by %s)", user_id, added_by)
    result = (
        _get_client()
        .table("allowed_users")
        .upsert({"user_id": user_id, "added_by": added_by}, on_conflict="user_id")
        .execute()
    )
    if not result.data:
        raise RuntimeError(f"Insert into 'allowed_users' returned no data: {result}")
    return result.data[0]


def remove_allowed_user(user_id: str) -> bool:
    logger.info("Revoking user %s", user_id)
    result = _get_client().table("allowed_users").delete().eq("user_id", user_id).execute()
    return len(result.data) > 0


def list_allowed_users() -> list:
    return _get_client().table("allowed_users").select("*").execute().data
```

- [ ] **Step 5: Run to verify pass**

Run: `python3 -m pytest tests/test_db.py -k "allowed or is_user" -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Lint and commit**

Run: `python3 -m ruff check db/client.py tests/test_db.py` (no new errors).

```bash
git add db/schema.sql db/client.py tests/test_db.py
git commit -m "feat: add allowed_users table and allowlist helpers"
```

---

## Task 2: DM-only auth gate + owner admin commands

**Files:**
- Modify: `bot/client.py`
- Test: `tests/test_bot_client.py` (create)

Discord event handlers are awkward to unit-test directly, so we extract the authorization decision and the owner check into pure, testable helpers, and keep the handlers thin.

- [ ] **Step 1: Write the failing tests** — create `tests/test_bot_client.py`:

```python
from unittest.mock import MagicMock

import pytest


def test_is_owner_true(monkeypatch):
    from bot import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    assert client._is_owner("owner123") is True


def test_is_owner_false(monkeypatch):
    from bot import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    assert client._is_owner("someone_else") is False
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_bot_client.py -v`
Expected: FAIL — `AttributeError: module 'bot.client' has no attribute '_is_owner'`.

- [ ] **Step 3: Implement in `bot/client.py`**

Add an owner helper near the top (after the imports / `_CHANNEL_ID` block):

```python
def _is_owner(user_id: str) -> bool:
    load_dotenv()
    return user_id == os.environ.get("OWNER_ID")
```

Replace the body of `on_message` with a DM-only auth gate (keep the function signature and the `message.author.bot` guard):

```python
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return  # DM-only

    from db.client import is_user_allowed

    user_id = str(message.author.id)
    if not await asyncio.to_thread(is_user_allowed, user_id):
        await message.channel.send("Sorry, you're not authorized to use this bot.")
        logger.info("Rejected unauthorized user %s", user_id)
        return

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
```

Add the three owner-only slash commands (after the existing `/resetmemory` command):

```python
@tree.command(name="allow", description="(Owner) Permit a user to use the bot")
@app_commands.describe(user="The user to permit")
async def allow(interaction: discord.Interaction, user: discord.User):
    if not _is_owner(str(interaction.user.id)):
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    from db.client import add_allowed_user
    await asyncio.to_thread(add_allowed_user, str(user.id), str(interaction.user.id))
    await interaction.response.send_message(f"✅ {user.mention} is now permitted.", ephemeral=True)


@tree.command(name="revoke", description="(Owner) Remove a user's access")
@app_commands.describe(user="The user to revoke")
async def revoke(interaction: discord.Interaction, user: discord.User):
    if not _is_owner(str(interaction.user.id)):
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    from db.client import remove_allowed_user
    removed = await asyncio.to_thread(remove_allowed_user, str(user.id))
    msg = f"🗑️ Revoked {user.mention}." if removed else f"{user.mention} wasn't permitted."
    await interaction.response.send_message(msg, ephemeral=True)


@tree.command(name="listusers", description="(Owner) List permitted users")
async def listusers(interaction: discord.Interaction):
    if not _is_owner(str(interaction.user.id)):
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    from db.client import list_allowed_users
    rows = await asyncio.to_thread(list_allowed_users)
    if not rows:
        await interaction.response.send_message("No permitted users yet (owner always allowed).", ephemeral=True)
        return
    lines = "\n".join(f"• <@{r['user_id']}>" for r in rows)
    await interaction.response.send_message(f"**Permitted users:**\n{lines}", ephemeral=True)
```

Remove the now-unused `_get_channel_id` function and the `_CHANNEL_ID` global (DM-only — `DISCORD_CHANNEL_ID` is no longer read). Remove the `_get_channel_id()` call in `on_ready` (keep the rest of `on_ready`).

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_bot_client.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Confirm the module still imports cleanly**

Run: `python3 -c "import bot.client; print('import ok')"`
Expected: `import ok` (no NameError from the removed channel code).

- [ ] **Step 6: Lint and commit**

Run: `python3 -m ruff check bot/client.py tests/test_bot_client.py` (no new errors).

```bash
git add bot/client.py tests/test_bot_client.py
git commit -m "feat: DM-only auth gate + owner /allow /revoke /listusers commands"
```

> **Manual step (do once before running):** add `OWNER_ID=<your Discord user id>` to `.env` and the CI secrets. `DISCORD_CHANNEL_ID` is no longer needed.

---

# PHASE 2 — Per-user data isolation

## Task 3: Schema — owner columns + composite uniqueness

**Files:**
- Modify: `db/schema.sql`

This task edits the source-of-truth schema and documents the live migration; applying it to Supabase is a manual operational step.

- [ ] **Step 1: Update `db/schema.sql`**

In the `games` table definition, add `user_id text not null` and change the inline `itad_id text not null unique` to `itad_id text not null` plus a table-level `unique (user_id, itad_id)`. In the `watches` table, add `user_id text not null` and change `swisstimehouse_url text null unique` to `swisstimehouse_url text null` plus `unique (user_id, swisstimehouse_url)`. Add indexes:

```sql
create index if not exists idx_games_user_id on games(user_id);
create index if not exists idx_watches_user_id on watches(user_id);
```

- [ ] **Step 2: Document + apply the live migration**

Run these in the Supabase SQL editor (replace `<OWNER_DISCORD_ID>` with the real id). First confirm the existing unique constraint names with `\d games` / `\d watches` (or the Supabase table view) — they are typically `games_itad_id_key` and `watches_swisstimehouse_url_key`:

```sql
alter table games   add column if not exists user_id text;
alter table watches add column if not exists user_id text;

update games   set user_id = '<OWNER_DISCORD_ID>' where user_id is null;
update watches set user_id = '<OWNER_DISCORD_ID>' where user_id is null;

alter table games   alter column user_id set not null;
alter table watches alter column user_id set not null;

alter table games   drop constraint if exists games_itad_id_key;
alter table games   add constraint games_user_itad_unique unique (user_id, itad_id);

alter table watches drop constraint if exists watches_swisstimehouse_url_key;
alter table watches add constraint watches_user_sth_unique unique (user_id, swisstimehouse_url);

create index if not exists idx_games_user_id on games(user_id);
create index if not exists idx_watches_user_id on watches(user_id);
```

Verify: `select user_id, count(*) from games group by user_id;` shows all rows under the owner id.

- [ ] **Step 3: Commit**

```bash
git add db/schema.sql
git commit -m "feat: add user_id owner column + composite uniqueness to games/watches"
```

---

## Task 4: Scope game DB helpers by user_id

**Files:**
- Modify: `db/client.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_db.py`:

```python
def test_get_games_scopes_to_user(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    chain = fake_table.select.return_value.eq.return_value
    chain.execute.return_value.data = [{"id": "g1", "user_id": "A"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    rows = client.get_games("A")
    fake_table.select.return_value.eq.assert_called_once_with("user_id", "A")
    assert rows == [{"id": "g1", "user_id": "A"}]


def test_get_games_no_user_returns_all(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.execute.return_value.data = [{"id": "g1"}, {"id": "g2"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    rows = client.get_games()
    fake_table.select.return_value.eq.assert_not_called()
    assert len(rows) == 2


def test_add_game_scopes_and_composite_conflict(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.upsert.return_value.execute.return_value.data = [{"id": "g1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    client.add_game("A", "Elden Ring", "itad1", target_price=500.0)
    args, kwargs = fake_table.upsert.call_args
    assert args[0]["user_id"] == "A"
    assert kwargs.get("on_conflict") == "user_id,itad_id"


def test_set_target_price_scoped(mocker):
    from db import client
    mocker.patch.object(client, "get_games", return_value=[{"id": "g1", "title": "Elden Ring"}])
    fake_table = mocker.MagicMock()
    fake_table.update.return_value.eq.return_value.execute.return_value.data = [{"id": "g1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.set_target_price("A", "elden ring", 400.0) is True
    client.get_games.assert_called_once_with("A")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_db.py -k "scopes or composite or scoped" -v`
Expected: FAIL — `TypeError` (signatures don't accept `user_id`).

- [ ] **Step 3: Implement the changes in `db/client.py`**

Replace `get_games`, `add_game`, `_find_game_by_title`, `set_target_price`, `remove_game`, and `get_recent_deals` with:

```python
def get_games(user_id: Optional[str] = None) -> list:
    query = _get_client().table("games").select("*")
    if user_id is not None:
        query = query.eq("user_id", user_id)
    return query.execute().data


def add_game(user_id: str, title: str, itad_id: str, target_price: Optional[float] = None) -> dict:
    logger.info("Adding game for %s: %s (itad_id=%s)", user_id, title, itad_id)
    row = {"user_id": user_id, "title": title, "itad_id": itad_id, "target_price": target_price}
    result = _get_client().table("games").upsert(row, on_conflict="user_id,itad_id").execute()
    if not result.data:
        raise RuntimeError(f"Insert into 'games' returned no data: {result}")
    return result.data[0]


def _find_game_by_title(user_id: str, title: str) -> Optional[dict]:
    return _fuzzy_find(get_games(user_id), title, "title")


def set_target_price(user_id: str, title: str, target_price: Optional[float]) -> bool:
    game = _find_game_by_title(user_id, title)
    if not game:
        return False
    result = (
        _get_client().table("games").update({"target_price": target_price})
        .eq("id", game["id"]).execute()
    )
    return len(result.data) > 0


def remove_game(user_id: str, title: str) -> bool:
    game = _find_game_by_title(user_id, title)
    if not game:
        return False
    result = _get_client().table("games").delete().eq("id", game["id"]).execute()
    return len(result.data) > 0


def get_recent_deals(user_id: str, limit: int = 5) -> list:
    return (
        _get_client().table("notifications_log")
        .select("*, games!inner(title, user_id)")
        .eq("games.user_id", user_id)
        .order("notified_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_db.py -k "scopes or composite or scoped" -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint and commit**

Run: `python3 -m ruff check db/client.py tests/test_db.py` (no new errors).

```bash
git add db/client.py tests/test_db.py
git commit -m "feat: scope game db helpers by user_id"
```

---

## Task 5: Scope watch DB helpers by user_id

**Files:**
- Modify: `db/client.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_db.py`:

```python
def test_get_watches_scopes_to_user(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.eq.return_value.execute.return_value.data = [{"id": "w1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    client.get_watches("A")
    fake_table.select.return_value.eq.assert_called_once_with("user_id", "A")


def test_add_watch_scopes_and_composite_conflict(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.upsert.return_value.execute.return_value.data = [{"id": "w1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    client.add_watch("A", name="Casio", brand="Casio", reference_no="G1",
                     target_price=30000.0, swisstimehouse_url="https://www.swisstimehouse.com/x")
    args, kwargs = fake_table.upsert.call_args
    assert args[0]["user_id"] == "A"
    assert kwargs.get("on_conflict") == "user_id,swisstimehouse_url"


def test_remove_watch_scoped(mocker):
    from db import client
    mocker.patch.object(client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}])
    fake_table = mocker.MagicMock()
    fake_table.delete.return_value.eq.return_value.execute.return_value.data = [{"id": "w1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.remove_watch("A", "Casio G1714") is True
    client.get_watches.assert_called_once_with("A")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_db.py -k "watch and (scope or composite)" -v`
Expected: FAIL — `TypeError` (signatures don't accept `user_id`).

- [ ] **Step 3: Implement in `db/client.py`**

Replace `get_watches`, `add_watch`, `_find_watch_by_name`, `set_watch_target`, `remove_watch` with:

```python
def get_watches(user_id: Optional[str] = None) -> list:
    query = _get_client().table("watches").select("*")
    if user_id is not None:
        query = query.eq("user_id", user_id)
    return query.execute().data


def add_watch(
    user_id: str,
    name: str,
    brand: Optional[str],
    reference_no: Optional[str],
    target_price: float,
    swisstimehouse_url: str,
) -> dict:
    logger.info("Adding watch for %s: %s (target=%s)", user_id, name, target_price)
    row = {
        "user_id": user_id,
        "name": name,
        "brand": brand,
        "reference_no": reference_no,
        "target_price": target_price,
        "swisstimehouse_url": swisstimehouse_url,
    }
    result = (
        _get_client().table("watches").upsert(row, on_conflict="user_id,swisstimehouse_url").execute()
    )
    if not result.data:
        raise RuntimeError(f"Insert into 'watches' returned no data: {result}")
    logger.info("Watch added/updated: %s", name)
    return result.data[0]


def _find_watch_by_name(user_id: str, name: str) -> Optional[dict]:
    return _fuzzy_find(get_watches(user_id), name, "name")


def set_watch_target(user_id: str, name: str, target_price: float) -> bool:
    logger.info("Setting watch target for %s/%s: %s", user_id, name, target_price)
    watch = _find_watch_by_name(user_id, name)
    if not watch:
        return False
    result = (
        _get_client().table("watches").update({"target_price": target_price})
        .eq("id", watch["id"]).execute()
    )
    return len(result.data) > 0


def remove_watch(user_id: str, name: str) -> bool:
    watch = _find_watch_by_name(user_id, name)
    if not watch:
        return False
    result = _get_client().table("watches").delete().eq("id", watch["id"]).execute()
    logger.info("Watch removed: %s", watch["name"])
    return len(result.data) > 0
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_db.py -k "watch and (scope or composite)" -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint and commit**

Run: `python3 -m ruff check db/client.py tests/test_db.py` (no new errors).

```bash
git add db/client.py tests/test_db.py
git commit -m "feat: scope watch db helpers by user_id"
```

---

## Task 6: Thread user_id through bot tools + dispatch

**Files:**
- Modify: `bot/functions.py`
- Test: `tests/test_bot_functions.py`

Every tool function takes `user_id` as its first parameter; `dispatch` injects it; the LLM-facing `TOOLS` schemas are unchanged except `clear_memory` (drop its `user_id` property so the LLM can't supply it).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_bot_functions.py`:

```python
def test_dispatch_injects_user_id(mocker):
    from bot.functions import dispatch
    mock_db = mocker.patch("bot.functions.db_get_games", return_value=[])
    dispatch("list_games", {}, "userA")
    mock_db.assert_called_once_with("userA")


def test_dispatch_add_game_passes_user_id(mocker):
    from bot.functions import dispatch
    mocker.patch("bot.functions.search_game", return_value={"id": "itad1", "title": "Elden Ring"})
    mock_add = mocker.patch("bot.functions.db_add_game", return_value={"title": "Elden Ring"})
    dispatch("add_game", {"title": "Elden Ring", "target_price": 500.0}, "userA")
    mock_add.assert_called_once_with("userA", "Elden Ring", "itad1", target_price=500.0)


def test_clear_memory_schema_has_no_user_id():
    from bot.functions import TOOLS
    tool = next(t for t in TOOLS if t["function"]["name"] == "clear_memory")
    assert "user_id" not in tool["function"]["parameters"]["properties"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_bot_functions.py -k "dispatch_injects or passes_user or clear_memory_schema" -v`
Expected: FAIL — `dispatch()` takes 2 args / `db_get_games` called with no args / `user_id` still in schema.

- [ ] **Step 3: Implement in `bot/functions.py`**

Give every tool function `user_id` as its first parameter and pass it into the scoped db calls. The full updated function bodies:

```python
def add_game(user_id: str, title: str, target_price: float = None) -> str:
    game = search_game(title)
    if game is None:
        return f"Sorry, '{title}' was not found on IsThereAnyDeal."
    db_add_game(user_id, game["title"], game["id"], target_price=target_price)
    if target_price is not None:
        return f"Tracking **{game['title']}**. I'll alert you when it drops below ₹{target_price:.2f}."
    return f"Tracking **{game['title']}**. I'll alert you when a deal drops."


def set_target_price(user_id: str, title: str, target_price: float = None) -> str:
    updated = db_set_target_price(user_id, title, target_price)
    if not updated:
        return f"**{title}** wasn't found in your watchlist."
    if target_price is None:
        return f"Removed target price for **{title}**. I'll now alert on historical lows."
    return f"Target price for **{title}** set to ₹{target_price:.2f}."


def remove_game(user_id: str, title: str) -> str:
    if db_remove_game(user_id, title):
        return f"No longer tracking **{title}**."
    return f"**{title}** wasn't in your watchlist."


def list_games(user_id: str) -> str:
    games = db_get_games(user_id)
    if not games:
        return "Your watchlist is empty. Try 'track <game name>' to add a game."
    lines = []
    for g in games:
        line = f"• {g['title']}"
        if g.get("target_price") is not None:
            line += f" (target: ₹{g['target_price']:.2f})"
        lines.append(line)
    return "**Games you're tracking:**\n" + "\n".join(lines)


def get_current_price(user_id: str, title: str) -> str:
    game = search_game(title)
    if game is None:
        return f"Sorry, '{title}' was not found on IsThereAnyDeal."
    prices = get_all_prices(game["id"])
    if not prices:
        return f"No current deals found for **{game['title']}**."
    lines = [f"**{game['title']}** prices:"]
    for p in prices[:10]:
        lines.append(f"• {p['store']}: ₹{p['price']:.2f} ({p['cut']}% off, was ₹{p['regular_price']:.2f})")
    return "\n".join(lines)


def get_historical_low_price(user_id: str, title: str) -> str:
    game = search_game(title)
    if game is None:
        return f"Sorry, '{title}' was not found on IsThereAnyDeal."
    low = get_historical_low(game["id"])
    if low is None:
        return f"No historical low data found for **{game['title']}**."
    return f"The all-time historical low for **{game['title']}** is ₹{low:.2f}."


def get_recent_deals(user_id: str) -> str:
    deals = db_get_recent_deals(user_id)
    if not deals:
        return "No recent deals found."
    lines = "\n".join(
        f"• **{d['games']['title']}** — ₹{d['price']:.2f}"
        f" (alerted {d['notified_at'][:10] if d['notified_at'] else 'unknown date'})"
        for d in deals
    )
    return f"**Recent deals I found:**\n{lines}"


def add_watch(user_id: str, url: str, target_price: float = None) -> str:
    watch = fetch_swisstimehouse(url)
    if watch is None:
        return (
            "Sorry, I couldn't read a price from that link. "
            "Make sure it's a swisstimehouse.com product page."
        )
    if target_price is None:
        return (
            f"**{watch['name']}** is currently ₹{watch['price']:.2f} on Swiss Time House. "
            f"What target price (in ₹) should I alert you below?"
        )
    db_add_watch(
        user_id,
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


def list_watches(user_id: str) -> str:
    watches = db_get_watches(user_id)
    if not watches:
        return "Your watch list is empty. Add one with a swisstimehouse.com product link."
    lines = ["**Watches you're tracking:**"]
    for w in watches:
        line = f"• {w['name']}"
        if w.get("target_price") is not None:
            line += f" (target: ₹{float(w['target_price']):.2f})"
        lines.append(line)
    return "\n".join(lines)


def get_watch_price(user_id: str, name: str) -> str:
    match = db_find_watch_by_name(user_id, name)
    if not match or not match.get("swisstimehouse_url"):
        return f"**{name}** isn't on your watch list."
    fetched = fetch_swisstimehouse(match["swisstimehouse_url"])
    if fetched is None:
        return f"I couldn't fetch the current price for **{match['name']}** right now."
    return f"**{match['name']}** is currently ₹{fetched['price']:.2f} on Swiss Time House."


def set_watch_target(user_id: str, name: str, target_price: float) -> str:
    if not db_set_watch_target(user_id, name, target_price):
        return f"**{name}** wasn't found in your watch list."
    return f"Target price for **{name}** set to ₹{target_price:.2f}."


def remove_watch(user_id: str, name: str) -> str:
    if db_remove_watch(user_id, name):
        return f"No longer tracking **{name}**."
    return f"**{name}** wasn't in your watch list."
```

Update the `db_find_watch_by_name` import alias to point at the now-2-arg function (it already imports `_find_watch_by_name as db_find_watch_by_name`; no change needed beyond the call signature above).

Change `clear_memory` to drop the no-longer-needed lookup arg note (signature stays `clear_memory(user_id: str)` — it already takes `user_id`). In the `clear_memory` entry inside `TOOLS`, change its `parameters` to an empty object:

```python
            "parameters": {"type": "object", "properties": {}, "required": []},
```

Finally, update `dispatch` to inject `user_id`:

```python
def dispatch(name: str, arguments: dict, user_id: str) -> str:
    """Execute a tool by name, injecting the current user_id as the first argument."""
    fn = _FUNCTION_MAP.get(name)
    if fn is None:
        logger.error("Unknown tool requested: %s", name)
        return f"Unknown tool: {name}"
    return fn(user_id, **(arguments or {}))
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_bot_functions.py -v`
Expected: all PASS. (Existing watch/game tool tests will need their `dispatch(...)` calls updated to pass a `user_id` and their direct function calls updated to pass `user_id` first — update those existing tests in this file accordingly; e.g. `add_watch("https://...", target_price=...)` becomes `add_watch("userA", "https://...", target_price=...)`, and `dispatch("add_watch", {...})` becomes `dispatch("add_watch", {...}, "userA")`. Mock assertions like `db_add_watch.assert_called_once_with(name=..., ...)` become `db_add_watch.assert_called_once_with("userA", name=..., ...)`.)

- [ ] **Step 5: Lint and commit**

Run: `python3 -m ruff check bot/functions.py tests/test_bot_functions.py` (no new errors).

```bash
git add bot/functions.py tests/test_bot_functions.py
git commit -m "feat: thread user_id through bot tools and dispatch"
```

---

## Task 7: Inject user_id in the graph

**Files:**
- Modify: `ai/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_graph.py`:

```python
def test_run_tool_forwards_user_id(mocker):
    from ai import graph
    mock_dispatch = mocker.patch("ai.graph.dispatch", return_value="ok")
    graph._run_tool("list_games", {}, "userA")
    mock_dispatch.assert_called_once_with("list_games", {}, "userA")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_graph.py::test_run_tool_forwards_user_id -v`
Expected: FAIL — `_run_tool` takes 2 args / `dispatch` called without `user_id`.

- [ ] **Step 3: Implement in `ai/graph.py`**

Change `_run_tool` to accept and forward `user_id`:

```python
@observe()
def _run_tool(name: str, arguments: dict, user_id: str) -> str:
    """Execute a single tool call and record it as a child Langfuse span."""
    get_client().update_current_span(name=f"tool:{name}", input=arguments)
    try:
        result = dispatch(name, arguments, user_id)
    except Exception as exc:
        get_client().update_current_span(output=f"Error: {exc}", level="ERROR")
        raise
    get_client().update_current_span(output=result)
    return result
```

In `execute_tools`, pass `state["user_id"]` to `_run_tool`:

```python
            result = _run_tool(tc["name"], tc.get("arguments") or {}, state["user_id"])
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_graph.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

Run: `python3 -m ruff check ai/graph.py tests/test_graph.py` (no new errors).

```bash
git add ai/graph.py tests/test_graph.py
git commit -m "feat: inject user_id into tool dispatch from the graph"
```

---

# PHASE 3 — Per-user DM delivery

## Task 8: `send_dm` via bot token + Discord REST

**Files:**
- Modify: `utils/discord.py`
- Test: `tests/test_discord_webhook.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_discord_webhook.py`:

```python
def test_send_dm_opens_channel_and_posts(mocker, monkeypatch):
    from utils import discord

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
    open_resp = mocker.MagicMock()
    open_resp.json.return_value = {"id": "dm123"}
    open_resp.raise_for_status.return_value = None
    msg_resp = mocker.MagicMock()
    msg_resp.raise_for_status.return_value = None
    mock_post = mocker.patch("utils.discord.requests.post", side_effect=[open_resp, msg_resp])

    discord.send_dm("user42", "hello there")

    assert mock_post.call_count == 2
    open_call, msg_call = mock_post.call_args_list
    assert open_call.args[0].endswith("/users/@me/channels")
    assert open_call.kwargs["json"] == {"recipient_id": "user42"}
    assert msg_call.args[0].endswith("/channels/dm123/messages")
    assert msg_call.kwargs["json"] == {"content": "hello there"}
    assert "Bot tok" in open_call.kwargs["headers"]["Authorization"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_discord_webhook.py::test_send_dm_opens_channel_and_posts -v`
Expected: FAIL — `module 'utils.discord' has no attribute 'send_dm'`.

- [ ] **Step 3: Implement in `utils/discord.py`**

Append:

```python
_DISCORD_API = "https://discord.com/api/v10"


def send_dm(user_id: str, message: str) -> None:
    """DM a user via the bot token: open (or fetch) the DM channel, then post."""
    load_dotenv()
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise EnvironmentError("DISCORD_BOT_TOKEN is not set. Add it to your .env file.")
    headers = {"Authorization": f"Bot {token}"}
    open_resp = requests.post(
        f"{_DISCORD_API}/users/@me/channels", headers=headers, json={"recipient_id": user_id}
    )
    open_resp.raise_for_status()
    channel_id = open_resp.json()["id"]
    msg_resp = requests.post(
        f"{_DISCORD_API}/channels/{channel_id}/messages", headers=headers, json={"content": message}
    )
    msg_resp.raise_for_status()
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_discord_webhook.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

Run: `python3 -m ruff check utils/discord.py tests/test_discord_webhook.py` (no new errors).

```bash
git add utils/discord.py tests/test_discord_webhook.py
git commit -m "feat: add send_dm via bot token + Discord REST"
```

---

## Task 9: Cron DMs the owner; skips revoked owners

**Files:**
- Modify: `cron/price_check.py`
- Test: `tests/test_cron.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_cron.py`:

```python
def test_process_game_dms_owner(sample_game, mocker):
    from cron.price_check import process_game
    game = {**sample_game, "user_id": "ownerA"}
    mocker.patch("cron.price_check.get_best_price",
                 return_value={"price": 14.99, "regular_price": 59.99, "store": "Steam", "cut": 75})
    mocker.patch("cron.price_check.insert_price_history", return_value={})
    mocker.patch("cron.price_check.get_historical_low", return_value=14.99)
    mocker.patch("cron.price_check.get_last_notified_price", return_value=None)
    mocker.patch("cron.price_check.is_user_allowed", return_value=True)
    prov = MagicMock(); prov.generate_text.return_value = "Buy!"
    mocker.patch("cron.price_check.get_provider", return_value=prov)
    mock_dm = mocker.patch("cron.price_check.send_dm")
    mocker.patch("cron.price_check.log_notification")
    process_game(game)
    mock_dm.assert_called_once()
    assert mock_dm.call_args.args[0] == "ownerA"


def test_process_game_skips_revoked_owner(sample_game, mocker):
    from cron.price_check import process_game
    game = {**sample_game, "user_id": "revoked"}
    mocker.patch("cron.price_check.get_best_price",
                 return_value={"price": 14.99, "regular_price": 59.99, "store": "Steam", "cut": 75})
    mocker.patch("cron.price_check.insert_price_history", return_value={})
    mocker.patch("cron.price_check.get_historical_low", return_value=14.99)
    mocker.patch("cron.price_check.get_last_notified_price", return_value=None)
    mocker.patch("cron.price_check.is_user_allowed", return_value=False)
    mock_dm = mocker.patch("cron.price_check.send_dm")
    process_game(game)
    mock_dm.assert_not_called()


def test_process_watch_dms_owner(sample_watch, mocker):
    from cron.price_check import process_watch
    watch = {**sample_watch, "user_id": "ownerA"}
    mocker.patch("cron.price_check.fetch_swisstimehouse",
                 return_value={"name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 29000.0})
    mocker.patch("cron.price_check.insert_watch_price_history")
    mocker.patch("cron.price_check.get_last_watch_notified_price", return_value=None)
    mocker.patch("cron.price_check.is_user_allowed", return_value=True)
    prov = MagicMock(); prov.generate_text.return_value = "Buy!"
    mocker.patch("cron.price_check.get_provider", return_value=prov)
    mock_dm = mocker.patch("cron.price_check.send_dm")
    mocker.patch("cron.price_check.log_watch_notification")
    process_watch(watch)
    mock_dm.assert_called_once()
    assert mock_dm.call_args.args[0] == "ownerA"
```

The `sample_game` fixture in this file currently lacks `user_id`; the tests add it via `{**sample_game, "user_id": ...}`, so no fixture change is required.

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_cron.py -k "dms_owner or revoked" -v`
Expected: FAIL — `cron.price_check` has no `send_dm` / `is_user_allowed` import.

- [ ] **Step 3: Implement in `cron/price_check.py`**

Update imports: add `is_user_allowed` to the `db.client` import block, and import `send_dm` from `utils.discord` (keep `send_deal_alert`/`send_watch_alert` import or replace — they're no longer used after this task; remove them to avoid dead imports):

```python
from db.client import (
    get_games,
    get_last_notified_price,
    get_last_watch_notified_price,
    get_watches,
    insert_price_history,
    insert_watch_price_history,
    is_user_allowed,
    log_notification,
    log_watch_notification,
)
from utils.discord import send_dm
```

In `process_game`, after the deal + dedup checks pass and commentary is generated, replace the `send_deal_alert(...)` call with an authorization check + DM:

```python
    owner = game["user_id"]
    if not is_user_allowed(owner):
        logger.info("[%s] Owner %s no longer permitted, skipping alert.", title, owner)
        return
    message = (
        f"**Deal Alert: {title}**\n"
        f"₹{price_data['price']:.2f} on {price_data['store']} "
        f"({price_data['cut']}% off, was ₹{price_data['regular_price']:.2f})\n"
        f"{commentary}"
    )
    send_dm(owner, message)
    log_notification(game["id"], price_data["price"])
```

In `process_watch`, similarly replace the `send_watch_alert(...)` call:

```python
    owner = watch["user_id"]
    if not is_user_allowed(owner):
        logger.info("[%s] Owner %s no longer permitted, skipping alert.", name, owner)
        return
    message = (
        f"**Watch Deal Alert: {name}**\n"
        f"₹{price:.2f} on {seller} (target was ₹{target:.2f})\n"
        f"{commentary}"
    )
    send_dm(owner, message)
    log_watch_notification(watch["id"], price, seller)
```

(`sweep_games()`/`sweep_watches()` already call `get_games()`/`get_watches()` with no argument, which now returns all users' rows — no change needed there.)

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_cron.py -v`
Expected: all PASS. (Update the pre-existing `test_process_game_sends_alert_when_deal_detected` / `test_process_watch_sends_alert_below_target` tests: they assert on `send_deal_alert`/`send_watch_alert` — change them to patch `cron.price_check.send_dm` and `cron.price_check.is_user_allowed` (return True), add `user_id` to the sample dicts, and assert `send_dm` was called with the owner id. The `sample_game`/`sample_watch` fixtures should gain a `"user_id": "ownerA"` key so all watch/game process tests have an owner.)

- [ ] **Step 5: Lint and commit**

Run: `python3 -m ruff check cron/price_check.py tests/test_cron.py` (no new errors).

```bash
git add cron/price_check.py tests/test_cron.py
git commit -m "feat: cron DMs the owning user and skips revoked owners"
```

---

## Task 10: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Full suite**

Run: `python3 -m pytest -q`
Expected: all pass except the known pre-existing `tests/test_db.py::test_remove_game_deletes_row` (unrelated; if it now errors differently because `remove_game` gained a `user_id` arg, update that one test to call `remove_game("ownerA", "Elden Ring")` and mock `get_games`/`_get_client` accordingly — fixing it here is in-scope since the signature changed).

- [ ] **Step 2: Lint**

Run: `python3 -m ruff check .`
Expected: no new errors beyond the pre-existing legacy E501 lines.

- [ ] **Step 3: Import smoke test**

Run: `python3 -c "import bot.client, ai.graph, cron.price_check, bot.functions, utils.discord, db.client; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Manual operational steps (record as done)**

- Apply the Task 3 migration SQL in Supabase (with the real owner id); verify all existing games/watches are owned by the owner.
- Add `OWNER_ID=<your Discord id>` to `.env` and to GitHub Actions secrets (both workflows) and the Mac-mini container env.
- Confirm `DISCORD_BOT_TOKEN` is available to the cron (already a secret).
- Redeploy the bot container; re-sync `main` on the Mac mini.
- In Discord: DM the bot as the owner (should work); `/allow @friend`; have the friend DM the bot (should work); a non-permitted account DMing should get "not authorized".

- [ ] **Step 5: Final commit (if any test fixups were made)**

```bash
git add -A
git commit -m "test: multi-user verification fixups"
```

---

## Self-Review Notes (spec coverage)

- `allowed_users` + helpers + `OWNER_ID` bootstrap → Task 1 ✓
- DM-only gate + `/allow` `/revoke` `/listusers` → Task 2 ✓
- owner column + composite uniqueness + migration → Task 3 ✓
- game helpers scoped by user_id (incl. `get_games(None)` = all for cron) → Task 4 ✓
- watch helpers scoped by user_id → Task 5 ✓
- tools take user_id + `dispatch(name, args, user_id)` + clear_memory schema → Task 6 ✓
- graph injects `state["user_id"]` → Task 7 ✓
- `send_dm` via bot token/REST → Task 8 ✓
- cron DMs owner + skips revoked + sweeps all users → Task 9 ✓
- verification + manual migration/env/deploy → Task 10 ✓
- Signature consistency: `get_games(user_id=None)`, `add_game(user_id, title, itad_id, target_price)`, `_find_game_by_title(user_id, title)`, `get_watches(user_id=None)`, `add_watch(user_id, ...)`, `dispatch(name, args, user_id)`, `_run_tool(name, args, user_id)`, `send_dm(user_id, message)`, `is_user_allowed(user_id)` — consistent across tasks ✓
