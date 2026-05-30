# Watch Tracking — Design Spec

**Date:** 2026-05-30
**Status:** Approved, ready for implementation plan
**Scope:** v1 — track watches from swisstimehouse.com by URL, with a schema ready for additional sources (Myntra, official brand sites) that are not yet built.

## Background

DropHunter currently tracks **game** prices via the IsThereAnyDeal (ITAD) API. ITAD does the heavy lifting: one API call returns prices across ~10 stores plus an all-time historical low, keyed off a canonical product ID. The `games` table, the cron sweep, and the LLM tools all assume this aggregator exists.

There is **no ITAD-equivalent for watches.** This feature adds a parallel path for tracking watch prices from authentic sellers, starting with a single source.

## Goals

- Let a user track a watch by pasting its **swisstimehouse.com product URL** and setting a **required target price**.
- The background cron sweep re-fetches the page, records the price over time, and fires a Discord alert when the price drops to or below the target.
- The data model is designed for **multiple price sources** (swisstimehouse, Myntra, brand sites) so future sources slot in without a schema migration — but only swisstimehouse is implemented in v1.

## Non-Goals (v1)

- Myntra scraping (schema is ready; the scraper is **not** built — see Deferred Work).
- Official brand-site comparison (e.g. casio.in).
- Cross-site automatic product matching — the user asserts "same watch" by pasting each site's specific product URL.
- A historical-low data source for watches — there is none; we accumulate our own history over time, which is why **target price is required** (unlike games, where it is optional).

## Key Decisions (from brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Price source | Direct page fetch of the pasted URL | No reliable watch aggregator; one known site is cheap and reliable to parse |
| Code structure | Separate `watches` path parallel to the game path | Zero risk to the working game flow |
| Seller trust | Curated authentic sellers; v1 = swisstimehouse only | User wants authentic sellers, not marketplaces/gray-market |
| Multi-source storage | **Wide columns** (`swisstimehouse_price`, `myntra_price`) | Matches the mental model; lowest available price wins |
| Unavailable source | Stored as `NULL` | A blocked/absent source must not break the alert; lowest *available* price drives it |
| Price extraction | Deterministic HTML parse (BeautifulSoup), not LLM | Runs every sweep; must be free/fast; isolated and logs loudly on layout change |
| Target price | **Required** for watches | No historical-low fallback exists |

## Architecture

A parallel watch path that reuses the existing notification/dedup/Discord infrastructure but swaps the price source:

```
User pastes swisstimehouse URL + target  ──▶ add_watch tool
                                               │ fetch_swisstimehouse(url)
                                               ▼
                                          watches table (target_price required)

cron run()  ──▶ process_watch(watch) for each watch
                  │ fetch_swisstimehouse(url)  (myntra deferred → NULL)
                  ▼
              watch_price_history snapshot (per-source prices, NULL = unavailable)
                  │ lowest available price ≤ target_price AND < last notified?
                  ▼
              Discord alert (names winning seller, AI commentary) + watch_notifications_log
```

## Data Model

Three new tables. The `games`, `price_history`, and `notifications_log` tables are **untouched**.

```sql
create table if not exists watches (
    id uuid primary key default gen_random_uuid(),
    name text not null,                         -- "Casio G-Shock GM-B2100SD-1CDR"
    brand text null,
    reference_no text null,                     -- model/ref, e.g. "GM-B2100SD-1CDR"
    target_price numeric not null,              -- REQUIRED (no historical-low fallback)
    swisstimehouse_url text null,
    myntra_url text null,                       -- reserved for v2; always NULL in v1
    added_at timestamptz not null default now()
    -- app-enforced: at least one source URL must be present
);

create table if not exists watch_price_history (
    id uuid primary key default gen_random_uuid(),
    watch_id uuid not null references watches(id) on delete cascade,
    swisstimehouse_price numeric null,          -- NULL = absent/blocked
    myntra_price numeric null,                  -- NULL until v2
    fetched_at timestamptz not null default now()
);

create table if not exists watch_notifications_log (
    id uuid primary key default gen_random_uuid(),
    watch_id uuid not null references watches(id) on delete cascade,
    price numeric not null,
    seller text not null,                       -- which source won the alert
    notified_at timestamptz not null default now()
);

create index if not exists idx_watch_price_history_watch_id on watch_price_history(watch_id);
create index if not exists idx_watch_notifications_log_watch_id on watch_notifications_log(watch_id);
```

**Alert condition:** the lowest non-NULL price across source columns, compared against `target_price`, deduped so we only re-alert when the new price is lower than the last notified price.

## Components

### `utils/watches.py` (new, parallel to `utils/itad.py`)

- `fetch_swisstimehouse(url) -> dict | None`
  - Validates the URL host is `swisstimehouse.com`.
  - Fetches the page with `requests` (existing dep) and a normal browser User-Agent.
  - Parses with BeautifulSoup (new dep) targeting the price element. The product page has **no JSON-LD / schema.org markup** — the price is plain HTML text (observed: regular `₹ 49,995`, reduced `₹ 34,997`, "Save 30%"). The parser extracts the reduced (current) price and the regular price, and the product title (for `name`/`brand`/`reference`).
  - Returns `{name, brand, reference, price, regular_price}`, or `None` if the price element cannot be found — logging loudly at WARNING so a layout change is obvious.
  - Isolated in one small function so a future site-HTML change is a one-spot fix.
- `fetch_myntra(url)` — **deferred**, not implemented in v1 (documented stub at most). Myntra is JS-rendered and bot-protected; it will require spoofed headers, its internal product JSON, or a headless browser. When built, it returns a price or `None`.

### `bot/functions.py` (new tools, registered in `TOOLS` + `_FUNCTION_MAP`)

- `add_watch(swisstimehouse_url, target_price=None)`
  - Validates and fetches the URL. If not found/parseable, returns a clear error.
  - If `target_price` is omitted, the bot replies with the current price and **asks the user for a target** (it does not store yet).
  - **Upserts** the watch (on `swisstimehouse_url`), so re-adding later with a different/added source fills it in without duplicating.
  - On success, replies with the current price and the configured target.
- `list_watches()` — lists tracked watches with their target prices and latest known price.
- `get_watch_price(name)` — fuzzy-matches a tracked watch by name (reuse the `_normalize`/`_find` pattern from `db/client.py`) and returns its current price(s).
- `set_watch_target(name, target_price)` — updates the target.
- `remove_watch(name)` — removes a watch.
- Graph system prompt (`ai/graph.py`) extended: DropHunter also tracks watches; watches are added by pasting a swisstimehouse.com URL and require a target price.

### `db/client.py` (new helpers, parallel to game helpers)

- `add_watch`, `get_watches`, `set_watch_target`, `remove_watch` (fuzzy match by name).
- `insert_watch_price_history(watch_id, swisstimehouse_price, myntra_price)`.
- `get_last_watch_notified_price(watch_id)`, `log_watch_notification(watch_id, price, seller)`.

### `cron/price_check.py` (new `process_watch`, added to `run()`)

`process_watch(watch)`:
1. Fetch each configured source (v1: swisstimehouse only; myntra → `None`).
2. Insert a `watch_price_history` snapshot with per-source prices.
3. Compute the lowest **non-NULL** price and which seller it came from.
4. If lowest ≤ `target_price` **and** lower than the last notified price → generate AI commentary (reuse `get_provider().generate_text`), send a Discord alert via a thin watch wrapper around `utils/discord.py`, and log the notification.
5. Errors per watch are caught and logged without aborting the sweep (mirror the existing game loop).

`run()` runs the existing game loop, then the watch loop.

### `utils/discord.py`

Add `send_watch_alert(...)` (thin wrapper / parallel to `send_deal_alert`) showing watch name, winning seller, current price, target, and AI commentary. Reuse the webhook plumbing.

## Error Handling

- swisstimehouse fetch failure or unparseable price → `None`, logged at WARNING; the watch is skipped that sweep (no false alert).
- Invalid/non-swisstimehouse URL on `add_watch` → clear user-facing error, nothing stored.
- DB errors in the watch loop are caught per-watch so one failure doesn't abort the sweep.

## Testing

Unit tests parallel to the existing suite:
- `fetch_swisstimehouse` against a **saved HTML fixture** of a real product page (price + title extraction, and the `None` path when the price element is absent).
- URL host validation (accept swisstimehouse.com, reject others).
- Lowest-available-price selection with `None` handling (one source NULL, both NULL).
- `process_watch` target + dedup logic with mocked fetch and DB (alerts at/below target, suppresses when not lower than last notified, skips when price unavailable).

## New Dependency

- `beautifulsoup4` (added to `requirements.txt` / `pyproject.toml`). `requests` is already present.

## Deferred Work (v2+)

- **Myntra** as a second source: implement `fetch_myntra`, populate `myntra_price`/`myntra_url`, accept the Myntra URL in `add_watch`. The wide-column schema and `least(available)` alert logic already accommodate it.
- **Official brand sites** (e.g. casio.in keyed off brand) as further sources.
- Generalizing `games` + `watches` into a single `products` abstraction if a third product type appears (YAGNI for now).
