import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

logger = logging.getLogger("drophunter.db")

_conn = None


def _ensure_conn():
    global _conn
    if _conn is None or _conn.closed:
        load_dotenv()
        dsn = os.environ["LOCAL_DB_URL"]
        logger.info("Connecting to local Postgres")
        _conn = psycopg2.connect(dsn)
        _conn.autocommit = True
        logger.info("Postgres connection established")
    return _conn


@contextmanager
def _cursor():
    conn = _ensure_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
    except psycopg2.OperationalError:
        global _conn
        _conn = None
        raise


def _row(r) -> dict:
    """Convert a RealDictRow to a plain dict, serializing datetimes to ISO strings."""
    result = {}
    for k, v in r.items():
        result[k] = v.isoformat() if isinstance(v, datetime) else v
    return result


def _rows(rs) -> list:
    return [_row(r) for r in rs]


# ---------------------------------------------------------------------------
# Game helpers
# ---------------------------------------------------------------------------

def get_games(user_id: Optional[str] = None) -> list:
    with _cursor() as cur:
        if user_id is not None:
            cur.execute(
                "SELECT * FROM drophunter.games WHERE user_id = %s ORDER BY added_at",
                (user_id,),
            )
        else:
            cur.execute("SELECT * FROM drophunter.games ORDER BY added_at")
        rows = _rows(cur.fetchall())
    logger.debug("Fetched %d game(s) for user_id=%s", len(rows), user_id)
    return rows


def add_game(user_id: str, title: str, itad_id: str, target_price: Optional[float] = None) -> dict:
    logger.info("Adding game for %s: %s (itad_id=%s)", user_id, title, itad_id)
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO drophunter.games (user_id, title, itad_id, target_price)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, itad_id) DO UPDATE
                SET title = EXCLUDED.title, target_price = EXCLUDED.target_price
            RETURNING *
            """,
            (user_id, title, itad_id, target_price),
        )
        return _row(cur.fetchone())


def _normalize(text: str) -> str:
    return re.sub(r'[^a-z0-9 ]', '', text.lower()).strip()


def _fuzzy_find(rows: list, query: str, key: str) -> Optional[dict]:
    norm_query = _normalize(query)
    for r in rows:
        if _normalize(r[key]) == norm_query:
            return r
    for r in rows:
        if norm_query in _normalize(r[key]) or _normalize(r[key]) in norm_query:
            return r
    return None


def _find_game_by_title(user_id: str, title: str) -> Optional[dict]:
    return _fuzzy_find(get_games(user_id), title, "title")


def set_target_price(user_id: str, title: str, target_price: Optional[float]) -> bool:
    game = _find_game_by_title(user_id, title)
    if not game:
        logger.warning("No game matched '%s' for target price update", title)
        return False
    with _cursor() as cur:
        cur.execute(
            "UPDATE drophunter.games SET target_price = %s WHERE id = %s",
            (target_price, game["id"]),
        )
        return cur.rowcount > 0


def remove_game(user_id: str, title: str) -> bool:
    game = _find_game_by_title(user_id, title)
    if not game:
        logger.warning("No game matched '%s' for removal", title)
        return False
    with _cursor() as cur:
        cur.execute("DELETE FROM drophunter.games WHERE id = %s", (game["id"],))
        return cur.rowcount > 0


def insert_price_history(game_id: str, price: float, regular_price: float, store: str) -> dict:
    logger.debug("Inserting price history: game_id=%s price=%.2f store=%s", game_id, price, store)
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO drophunter.price_history (game_id, price, regular_price, store)
            VALUES (%s, %s, %s, %s)
            RETURNING *
            """,
            (game_id, price, regular_price, store),
        )
        return _row(cur.fetchone())


def get_last_notified_price(game_id: str) -> Optional[float]:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT price FROM drophunter.notifications_log
            WHERE game_id = %s
            ORDER BY notified_at DESC
            LIMIT 1
            """,
            (game_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    price = float(row["price"])
    logger.debug("Last notified price for %s: ₹%.2f", game_id, price)
    return price


def log_notification(game_id: str, price: float) -> dict:
    logger.info("Logging notification: game_id=%s price=%.2f", game_id, price)
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO drophunter.notifications_log (game_id, price) VALUES (%s, %s) RETURNING *",
            (game_id, price),
        )
        return _row(cur.fetchone())


def get_recent_deals(user_id: str, limit: int = 5) -> list:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT nl.id, nl.game_id, nl.price, nl.notified_at,
                   g.title AS game_title, g.user_id AS game_user_id
            FROM drophunter.notifications_log nl
            JOIN drophunter.games g ON nl.game_id = g.id
            WHERE g.user_id = %s
            ORDER BY nl.notified_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
    result = []
    for r in rows:
        d = _row(r)
        d["games"] = {"title": d.pop("game_title"), "user_id": d.pop("game_user_id")}
        result.append(d)
    return result


def get_historical_low(game_id: str) -> Optional[float]:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT price FROM drophunter.price_history
            WHERE game_id = %s
            ORDER BY price ASC
            LIMIT 1
            """,
            (game_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return float(row["price"])


def was_recently_notified(game_id: str, hours: int = 6) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with _cursor() as cur:
        cur.execute(
            """
            SELECT id FROM drophunter.notifications_log
            WHERE game_id = %s AND notified_at >= %s
            LIMIT 1
            """,
            (game_id, cutoff),
        )
        return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Chat memory helpers
# ---------------------------------------------------------------------------

def get_chat_context(user_id: str) -> dict:
    try:
        with _cursor() as cur:
            cur.execute(
                "SELECT summary FROM drophunter.chat_summary WHERE user_id = %s",
                (user_id,),
            )
            summary_row = cur.fetchone()
            summary = summary_row["summary"] if summary_row else None

            cur.execute(
                """
                SELECT role, content FROM drophunter.chat_messages
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (user_id,),
            )
            messages = list(reversed([dict(r) for r in cur.fetchall()]))
        return {"summary": summary, "messages": messages}
    except Exception as exc:
        logger.warning("Failed to load chat context for %s: %s", user_id, exc)
        return {"summary": None, "messages": []}


def save_turn(user_id: str, user_message: str, assistant_message: str) -> None:
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO drophunter.chat_messages (user_id, role, content) VALUES
            (%s, 'user', %s),
            (%s, 'assistant', %s)
            """,
            (user_id, user_message, user_id, assistant_message),
        )


def get_message_count(user_id: str) -> int:
    with _cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM drophunter.chat_messages WHERE user_id = %s",
            (user_id,),
        )
        return cur.fetchone()["cnt"]


def summarize_if_needed(user_id: str, gemini_provider) -> None:
    if get_message_count(user_id) <= 20:
        return

    with _cursor() as cur:
        cur.execute(
            """
            SELECT id, role, content FROM drophunter.chat_messages
            WHERE user_id = %s
            ORDER BY created_at ASC
            LIMIT 15
            """,
            (user_id,),
        )
        oldest = [dict(r) for r in cur.fetchall()]

    if not oldest:
        return

    with _cursor() as cur:
        cur.execute(
            "SELECT summary FROM drophunter.chat_summary WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
    existing_summary = row["summary"] if row else "None"

    messages_text = "\n".join(f"{m['role']}: {m['content']}" for m in oldest)
    prompt = (
        "You are a memory manager for a Discord game deal assistant called DropHunter.\n"
        "Summarize the following conversation messages into a concise paragraph (max 150 words).\n"
        "Focus on: games the user is tracking, price targets they have set, deals they were notified about,\n"
        "and any preferences they have expressed. Merge with the existing summary if provided.\n\n"
        f"Existing summary: {existing_summary}\n\n"
        f"Messages to summarize:\n{messages_text}"
    )

    new_summary = gemini_provider.generate_text(prompt)

    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO drophunter.chat_summary (user_id, summary, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET summary = EXCLUDED.summary, updated_at = EXCLUDED.updated_at
            """,
            (user_id, new_summary, datetime.now(timezone.utc)),
        )
        ids_to_delete = [m["id"] for m in oldest]
        cur.execute(
            "DELETE FROM drophunter.chat_messages WHERE id = ANY(%s)",
            (ids_to_delete,),
        )
    logger.info("Summarized %d messages for user %s", len(ids_to_delete), user_id)


def force_summarize(user_id: str, gemini_provider) -> str:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT id, role, content FROM drophunter.chat_messages
            WHERE user_id = %s
            ORDER BY created_at ASC
            """,
            (user_id,),
        )
        all_messages = [dict(r) for r in cur.fetchall()]

    if not all_messages:
        return "No conversation history to summarize."

    with _cursor() as cur:
        cur.execute(
            "SELECT summary FROM drophunter.chat_summary WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
    existing_summary = row["summary"] if row else "None"

    messages_text = "\n".join(f"{m['role']}: {m['content']}" for m in all_messages)
    prompt = (
        "You are a memory manager for a Discord game deal assistant called DropHunter.\n"
        "Summarize the following conversation into a concise paragraph (max 200 words).\n"
        "Focus ONLY on factual information:\n"
        "- Games the user is currently tracking (with their exact titles)\n"
        "- Target prices they have set\n"
        "- Any preferences they expressed\n"
        "Do NOT include any hallucinated or assumed information. Only include facts from the messages.\n"
        "Merge with the existing summary if provided.\n\n"
        f"Existing summary: {existing_summary}\n\n"
        f"Messages to summarize:\n{messages_text}"
    )

    new_summary = gemini_provider.generate_text(prompt)

    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO drophunter.chat_summary (user_id, summary, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET summary = EXCLUDED.summary, updated_at = EXCLUDED.updated_at
            """,
            (user_id, new_summary, datetime.now(timezone.utc)),
        )
        ids_to_delete = [m["id"] for m in all_messages]
        cur.execute(
            "DELETE FROM drophunter.chat_messages WHERE id = ANY(%s)",
            (ids_to_delete,),
        )
    logger.info("Force-summarized %d messages for user %s", len(ids_to_delete), user_id)
    return new_summary


def clear_memory(user_id: str) -> None:
    with _cursor() as cur:
        cur.execute("DELETE FROM drophunter.chat_messages WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM drophunter.chat_summary WHERE user_id = %s", (user_id,))
    logger.info("Cleared all memory for user %s", user_id)


# ---------------------------------------------------------------------------
# Watch helpers
# ---------------------------------------------------------------------------

def get_watches(user_id: Optional[str] = None) -> list:
    with _cursor() as cur:
        if user_id is not None:
            cur.execute(
                "SELECT * FROM drophunter.watches WHERE user_id = %s ORDER BY added_at",
                (user_id,),
            )
        else:
            cur.execute("SELECT * FROM drophunter.watches ORDER BY added_at")
        return _rows(cur.fetchall())


def add_watch(
    user_id: str,
    name: str,
    brand: Optional[str],
    reference_no: Optional[str],
    target_price: float,
    swisstimehouse_url: str,
) -> dict:
    logger.info("Adding watch for %s: %s (target=%s)", user_id, name, target_price)
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO drophunter.watches
                (user_id, name, brand, reference_no, target_price, swisstimehouse_url)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, swisstimehouse_url) DO UPDATE SET
                name = EXCLUDED.name,
                brand = EXCLUDED.brand,
                reference_no = EXCLUDED.reference_no,
                target_price = EXCLUDED.target_price
            RETURNING *
            """,
            (user_id, name, brand, reference_no, target_price, swisstimehouse_url),
        )
        row = _row(cur.fetchone())
    logger.info("Watch added/updated: %s", name)
    return row


def _find_watch_by_name(user_id: str, name: str) -> Optional[dict]:
    return _fuzzy_find(get_watches(user_id), name, "name")


def set_watch_target(user_id: str, name: str, target_price: float) -> bool:
    logger.info("Setting watch target for %s/%s: %s", user_id, name, target_price)
    watch = _find_watch_by_name(user_id, name)
    if not watch:
        return False
    with _cursor() as cur:
        cur.execute(
            "UPDATE drophunter.watches SET target_price = %s WHERE id = %s",
            (target_price, watch["id"]),
        )
        return cur.rowcount > 0


def remove_watch(user_id: str, name: str) -> bool:
    watch = _find_watch_by_name(user_id, name)
    if not watch:
        return False
    with _cursor() as cur:
        cur.execute("DELETE FROM drophunter.watches WHERE id = %s", (watch["id"],))
    logger.info("Watch removed: %s", watch["name"])
    return True


def insert_watch_price_history(
    watch_id: str,
    swisstimehouse_price: Optional[float],
    myntra_price: Optional[float] = None,
) -> dict:
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO drophunter.watch_price_history
                (watch_id, swisstimehouse_price, myntra_price)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (watch_id, swisstimehouse_price, myntra_price),
        )
        return _row(cur.fetchone())


def get_last_watch_notified_price(watch_id: str) -> Optional[float]:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT price FROM drophunter.watch_notifications_log
            WHERE watch_id = %s
            ORDER BY notified_at DESC
            LIMIT 1
            """,
            (watch_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return float(row["price"])


def log_watch_notification(watch_id: str, price: float, seller: str) -> dict:
    logger.info(
        "Logging watch notification: watch_id=%s price=%.2f seller=%s",
        watch_id, price, seller,
    )
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO drophunter.watch_notifications_log (watch_id, price, seller)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (watch_id, price, seller),
        )
        return _row(cur.fetchone())


# ---------------------------------------------------------------------------
# Allowlist helpers
# ---------------------------------------------------------------------------

def _owner_id() -> Optional[str]:
    load_dotenv()
    return os.environ.get("OWNER_ID")


def is_user_allowed(user_id: str) -> bool:
    if user_id == _owner_id():
        return True
    with _cursor() as cur:
        cur.execute(
            "SELECT user_id FROM drophunter.allowed_users WHERE user_id = %s",
            (user_id,),
        )
        return cur.fetchone() is not None


def add_allowed_user(user_id: str, added_by: str) -> dict:
    logger.info("Allowing user %s (by %s)", user_id, added_by)
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO drophunter.allowed_users (user_id, added_by)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET added_by = EXCLUDED.added_by
            RETURNING *
            """,
            (user_id, added_by),
        )
        return _row(cur.fetchone())


def remove_allowed_user(user_id: str) -> bool:
    logger.info("Revoking user %s", user_id)
    with _cursor() as cur:
        cur.execute(
            "DELETE FROM drophunter.allowed_users WHERE user_id = %s",
            (user_id,),
        )
        return cur.rowcount > 0


def list_allowed_users() -> list:
    with _cursor() as cur:
        cur.execute("SELECT * FROM drophunter.allowed_users")
        return _rows(cur.fetchall())
