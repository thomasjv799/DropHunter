# Multi-User Support — Design Spec

**Date:** 2026-05-31
**Status:** Approved, ready for implementation plan
**Scope:** Let an owner permit specific Discord users to use DropHunter privately over DM, with each person's watchlist, history, and deal alerts fully isolated from everyone else's.

## Background

DropHunter is a Discord bot. Today:
- **Identity is already available** per message: `bot/client.py` does `user_id = str(message.author.id)` and threads it into `run_graph(user_id, ...)`. No hashing or extra identification is needed — Discord provides a stable unique ID on every message.
- **Chat memory is already per-user:** `chat_messages` and `chat_summary` are keyed by `user_id`.
- **The watchlist is global:** `games`, `watches`, and their `price_history` / `notifications_log` / `watch_price_history` / `watch_notifications_log` tables have **no owner column**. Everyone shares one watchlist, and the cron fires alerts to a single shared `DISCORD_WEBHOOK_URL`. With multiple users this mixes everyone's data and broadcasts everyone's deals to one channel.
- **No authorization:** anyone in the configured channel — or who DMs the bot — can use it.

This feature adds the three things needed for safe multi-user use: authorization, per-user data isolation, and private per-user alert delivery.

## Goals

- Only an **owner** and users the owner **permits** can use the bot.
- Each permitted user interacts with the bot **privately over DM**; their watchlist, price history, and deal alerts are isolated from other users.
- Deal alerts are delivered as **DMs to the owning user**, not to a shared channel.
- The owner's existing (currently global) watchlist is preserved as the owner's own data.

## Non-Goals

- Hashing/anonymizing Discord IDs (incompatible with DMing users; chat tables already store raw IDs — see Key Decisions).
- Shared/global watchlists visible to multiple users.
- Server-channel usage (the bot becomes DM-only).
- Per-user API keys, billing, rate limiting, or roles beyond owner/permitted.

## Key Decisions (from brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Identity | Discord `author.id`, stored raw | Already threaded everywhere; not a secret |
| Hashing | **No** | Cron must DM the user → needs the real ID; chat tables already store raw IDs |
| Usage model | **DM-only** | Cleanest isolation; nobody sees another's watches/alerts |
| Authorization | `OWNER_ID` env bootstrap + `allowed_users` table via `/allow` `/revoke` `/listusers` | Auto-captures IDs via @mention; no restart to manage; clean bootstrap |
| Owner column | `user_id` on `games` and `watches` only | Children inherit ownership via FK; stays normalized |
| Uniqueness | `(user_id, itad_id)` and `(user_id, swisstimehouse_url)` | Two users may track the same game/watch |
| Alert delivery | Cron DMs via bot token + Discord REST | Works in short-lived cron; no always-on gateway client |
| Existing data | Backfill all rows with the owner's `user_id` | Zero data loss; owner keeps their current list |

## Architecture

```
DM from Discord user
      │ author.id
      ▼
 bot/client.py  ── authorized? (OWNER_ID or in allowed_users) ──no──▶ "not authorized" reply, stop
      │ yes
      ▼
 ai/graph.py  run_graph(user_id, text)
      │ injects user_id into every tool call
      ▼
 bot/functions.py dispatch(name, args, user_id) → fn(user_id, **args)
      │
      ▼
 db/client.py  every watchlist query scoped by user_id

cron/price_check.py  (separate process, per sweep)
      │ for each game/watch row (carries user_id)
      │ owner still permitted?  ──no──▶ skip
      ▼
 utils/discord.py send_dm(user_id, message)  ── bot token, Discord REST ──▶ user's DM
```

## Data Model

Add ownership and an allowlist. The `chat_messages` / `chat_summary` tables are unchanged (already per-user).

```sql
-- New: who may use the bot (owner is bootstrapped from env, not stored here)
create table if not exists allowed_users (
    user_id text primary key,
    added_by text null,
    added_at timestamptz not null default now()
);

-- games / watches gain an owner; children inherit via FK.
-- Migration order (run in Supabase SQL editor):
--   1. add column nullable
--   2. backfill existing rows with the owner's Discord id
--   3. set NOT NULL
--   4. replace the global unique constraint with a composite one
alter table games   add column if not exists user_id text;
alter table watches add column if not exists user_id text;

update games   set user_id = '<OWNER_DISCORD_ID>' where user_id is null;
update watches set user_id = '<OWNER_DISCORD_ID>' where user_id is null;

alter table games   alter column user_id set not null;
alter table watches alter column user_id set not null;

-- games.itad_id was UNIQUE globally; make it per-user
alter table games drop constraint if exists games_itad_id_key;
alter table games add constraint games_user_itad_unique unique (user_id, itad_id);

-- watches.swisstimehouse_url was UNIQUE globally; make it per-user
alter table watches drop constraint if exists watches_swisstimehouse_url_key;
alter table watches add constraint watches_user_sth_unique unique (user_id, swisstimehouse_url);

create index if not exists idx_games_user_id on games(user_id);
create index if not exists idx_watches_user_id on watches(user_id);
```

> The exact existing constraint names (`games_itad_id_key`, `watches_swisstimehouse_url_key`) must be confirmed against the live DB during implementation (`\d games`); the plan will verify before dropping.

`db/schema.sql` is updated to reflect the final shape (the source of truth); the live DB is migrated manually via the SQL editor (no migration runner in this repo).

## Components

### `db/client.py`
- **Allowlist helpers:** `is_user_allowed(user_id) -> bool` (true for `OWNER_ID` or any row in `allowed_users`), `add_allowed_user(user_id, added_by)`, `remove_allowed_user(user_id)`, `list_allowed_users() -> list`.
- **Scope every watchlist helper by `user_id`:** `get_games(user_id=None)` — a `user_id` scopes to that user (bot path), `None` returns **all** users' rows (cron sweep path); same for `get_watches(user_id=None)`. Plus `add_game(user_id, title, itad_id, target_price)` with `on_conflict="user_id,itad_id"`, `set_target_price(user_id, title, ...)`, `remove_game(user_id, title)`, `get_recent_deals(user_id, ...)`, and the watch equivalents (`add_watch(user_id, ...)` with `on_conflict="user_id,swisstimehouse_url"`, `set_watch_target(user_id, ...)`, `remove_watch(user_id, ...)`). `_fuzzy_find` is reused but fed only that user's rows.
- `get_last_notified_price` / watch equivalent stay keyed by `game_id`/`watch_id` (already per-row, hence implicitly per-user).
- `OWNER_ID` is read from env (helper `_owner_id()`), so `is_user_allowed` never needs a DB row for the owner.

### `bot/functions.py`
- Every tool function gains `user_id` as its first parameter: `add_game(user_id, title, target_price=None)`, `list_games(user_id)`, `get_current_price` (unchanged — read-only ITAD lookup, no user scope needed), `add_watch(user_id, url, target_price=None)`, etc.
- `dispatch(name, arguments, user_id)` calls `fn(user_id, **arguments)`. The LLM-facing `TOOLS` schemas are **unchanged** — `user_id` is never an LLM-supplied argument.
- `get_current_price` / `get_historical_low_price` are pure ITAD lookups and need no user scope, but for a uniform `dispatch` they still accept and ignore `user_id` (or `dispatch` only injects for scoped tools — implementation picks one; uniform-accept is simpler and chosen here).

### `ai/graph.py`
- `execute_tools` passes `state["user_id"]` into `dispatch(tc["name"], tc["arguments"], state["user_id"])`. No schema or prompt change.

### `bot/client.py`
- **Auth gate** in `on_message`: ignore non-DM messages; for DMs, if `not is_user_allowed(author.id)` reply once with a short "You're not authorized to use this bot." and return.
- **Owner-only slash commands:** `/allow @user`, `/revoke @user`, `/listusers` — each checks `interaction.user.id == OWNER_ID` first; `/allow` and `/revoke` write `allowed_users`; `/listusers` reads it. Existing `/clearmemory` / `/resetmemory` stay (now implicitly per-user, which they already are).
- Remove the channel-listening branch (`DISCORD_CHANNEL_ID`) — DM-only.

### `utils/discord.py`
- New `send_dm(user_id, message)`: uses `DISCORD_BOT_TOKEN` and Discord REST — `POST /users/@me/channels` with `{"recipient_id": user_id}` to open the DM channel, then `POST /channels/{id}/messages` with `{"content": message}`. Keeps the existing `_send_to_discord` for any legacy webhook use.

### `cron/price_check.py`
- `process_game` / `process_watch` send the alert via `send_dm(row["user_id"], message)` (composed from the existing alert text) instead of the shared webhook.
- Before alerting, skip rows whose owner is not currently permitted (`is_user_allowed(row["user_id"])`), so revoked users stop receiving DMs.
- The sweep calls `get_games()` / `get_watches()` with **no** `user_id` (returns all users' rows, each carrying `user_id`); the per-row owner drives DM delivery.

## Error Handling

- Unauthorized DM → single polite reply, no processing, logged at INFO.
- `send_dm` failure (user blocked DMs / left) → logged at WARNING, sweep continues to the next row (mirrors existing per-item try/except).
- Owner-only command invoked by a non-owner → ephemeral "owner only" reply, no state change.
- Missing `OWNER_ID` env → fail fast at startup with a clear `EnvironmentError`.

## Testing

- **Auth:** `is_user_allowed` true for owner and allowlisted, false for stranger; `add_allowed_user`/`remove_allowed_user`/`list_allowed_users` table ops (mocked Supabase).
- **Isolation:** `get_games(A)` excludes B's rows; same `itad_id` for A and B coexists (upsert keyed on `(user_id, itad_id)`).
- **Tool scoping:** `dispatch("add_game", {...}, user_id="A")` calls `db_add_game` with `user_id="A"`; `TOOLS` schema contains no `user_id`.
- **Graph:** `execute_tools` forwards `state["user_id"]` to `dispatch`.
- **DM delivery:** `send_dm` issues the two expected REST calls (mocked `requests`); `process_game` calls `send_dm` with the row's `user_id` and skips rows whose owner fails `is_user_allowed`.
- **Slash commands:** owner check rejects non-owner; `/allow` writes a row.

## Implementation Phasing (single spec, phased plan)

1. **Phase 1 — Authorization:** `allowed_users` table, `is_user_allowed`/admin helpers, `OWNER_ID`, auth gate + `/allow` `/revoke` `/listusers`, DM-only. (Bot is now locked down; watchlist still global.)
2. **Phase 2 — Data isolation:** owner columns + migration, scope all watchlist db helpers + bot tools + `dispatch`/graph injection by `user_id`.
3. **Phase 3 — DM delivery:** `send_dm`, switch `process_game`/`process_watch` to per-owner DMs, skip revoked owners.

Each phase is independently testable and leaves the app working.

## New / changed configuration

- New env var: `OWNER_ID` (the owner's Discord user ID).
- `DISCORD_CHANNEL_ID` no longer used (DM-only); `DISCORD_WEBHOOK_URL` becomes legacy/optional.
- `DISCORD_BOT_TOKEN` now also used by the cron (for `send_dm`) — already a CI secret.
