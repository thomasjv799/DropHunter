import logging
import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

"""
Supabase client and query helpers for DropHunter.

Tables: games, price_history, notifications_log
"""

logger = logging.getLogger("drophunter.db")

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        load_dotenv()
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        logger.info("Connecting to Supabase: %s", url)
        _client = create_client(url, key)
        logger.info("Supabase client initialized successfully")
    return _client


def get_games() -> list:
    logger.debug("Fetching all games from watchlist")
    data = _get_client().table("games").select("*").execute().data
    logger.debug("Found %d game(s)", len(data))
    return data


def add_game(title: str, itad_id: str, target_price: Optional[float] = None) -> dict:
    logger.info("Adding game: %s (itad_id=%s, target_price=%s)", title, itad_id, target_price)
    row = {"title": title, "itad_id": itad_id, "target_price": target_price}
    result = (
        _get_client()
        .table("games")
        .upsert(row, on_conflict="itad_id")
        .execute()
    )
    if not result.data:
        raise RuntimeError(f"Insert into 'games' returned no data: {result}")
    logger.info("Game added successfully: %s", title)
    return result.data[0]


def _normalize(text: str) -> str:
    """Strip non-alphanumeric chars for fuzzy title comparison."""
    import re
    return re.sub(r'[^a-z0-9 ]', '', text.lower()).strip()


def _find_game_by_title(title: str) -> Optional[dict]:
    """Find a game in the watchlist by fuzzy title match. Returns the row or None."""
    games = get_games()
    norm_query = _normalize(title)
    # Try exact normalized match first, then substring match
    for g in games:
        if _normalize(g["title"]) == norm_query:
            return g
    for g in games:
        if norm_query in _normalize(g["title"]) or _normalize(g["title"]) in norm_query:
            return g
    return None


def set_target_price(title: str, target_price: Optional[float]) -> bool:
    logger.info("Setting target price for %s: %s", title, target_price)
    game = _find_game_by_title(title)
    if not game:
        logger.warning("No game matched '%s' for target price update", title)
        return False
    result = (
        _get_client()
        .table("games")
        .update({"target_price": target_price})
        .eq("id", game["id"])
        .execute()
    )
    updated = len(result.data) > 0
    if updated:
        logger.info("Target price updated for '%s' (matched '%s'): %s", title, game["title"], target_price)
    return updated


def remove_game(title: str) -> bool:
    logger.info("Removing game: %s", title)
    game = _find_game_by_title(title)
    if not game:
        logger.warning("No game matched '%s' for removal", title)
        return False
    result = (
        _get_client().table("games").delete().eq("id", game["id"]).execute()
    )
    removed = len(result.data) > 0
    logger.info("Game removed: %s (found=%s)", game["title"], removed)
    return removed


def insert_price_history(
    game_id: str, price: float, regular_price: float, store: str
) -> dict:
    logger.debug(
        "Inserting price history: game_id=%s price=%.2f store=%s",
        game_id,
        price,
        store,
    )
    result = (
        _get_client()
        .table("price_history")
        .insert(
            {
                "game_id": game_id,
                "price": price,
                "regular_price": regular_price,
                "store": store,
            }
        )
        .execute()
    )
    if not result.data:
        raise RuntimeError(
            f"Insert into 'price_history' returned no data: {result}"
        )
    return result.data[0]



def get_last_notified_price(game_id: str) -> Optional[float]:
    """Return the price from the most recent notification for this game, or None."""
    result = (
        _get_client()
        .table("notifications_log")
        .select("price")
        .eq("game_id", game_id)
        .order("notified_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    price = float(result.data[0]["price"])
    logger.debug("Last notified price for %s: ₹%.2f", game_id, price)
    return price


def log_notification(game_id: str, price: float) -> dict:
    logger.info("Logging notification: game_id=%s price=%.2f", game_id, price)
    result = (
        _get_client()
        .table("notifications_log")
        .insert({"game_id": game_id, "price": price})
        .execute()
    )
    if not result.data:
        raise RuntimeError(
            f"Insert into 'notifications_log' returned no data: {result}"
        )
    return result.data[0]


def get_recent_deals(limit: int = 5) -> list:
    logger.debug("Fetching recent deals (limit=%d)", limit)
    return (
        _get_client()
        .table("notifications_log")
        .select("*, games(title)")
        .order("notified_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )


def get_historical_low(game_id: str) -> Optional[float]:
    """Return the lowest recorded price for a game, or None if no history."""
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


def was_recently_notified(game_id: str, hours: int = 6) -> bool:
    """Return True if a notification was sent for this game within the last `hours` hours."""
    from datetime import timedelta
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


def get_chat_context(user_id: str) -> dict:
    """Returns {'summary': str|None, 'messages': list[dict]} for a user. Never raises."""
    try:
        summary_result = (
            _get_client().table("chat_summary").select("summary").eq("user_id", user_id).execute()
        )
        summary = summary_result.data[0]["summary"] if summary_result.data else None

        messages_result = (
            _get_client()
            .table("chat_messages")
            .select("role,content")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        messages = list(reversed(messages_result.data))
        return {"summary": summary, "messages": messages}
    except Exception as exc:
        logger.warning("Failed to load chat context for %s: %s", user_id, exc)
        return {"summary": None, "messages": []}


def save_turn(user_id: str, user_message: str, assistant_message: str) -> None:
    _get_client().table("chat_messages").insert([
        {"user_id": user_id, "role": "user", "content": user_message},
        {"user_id": user_id, "role": "assistant", "content": assistant_message},
    ]).execute()


def get_message_count(user_id: str) -> int:
    result = (
        _get_client()
        .table("chat_messages")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    return result.count or 0


def summarize_if_needed(user_id: str, gemini_provider) -> None:
    """Summarize oldest 15 messages if total count exceeds 20. Never raises."""
    if get_message_count(user_id) <= 20:
        return

    oldest = (
        _get_client()
        .table("chat_messages")
        .select("id,role,content")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .limit(15)
        .execute()
    )
    if not oldest.data:
        return

    summary_result = (
        _get_client().table("chat_summary").select("summary").eq("user_id", user_id).execute()
    )
    existing_summary = summary_result.data[0]["summary"] if summary_result.data else "None"

    messages_text = "\n".join(f"{m['role']}: {m['content']}" for m in oldest.data)
    prompt = (
        "You are a memory manager for a Discord game deal assistant called DropHunter.\n"
        "Summarize the following conversation messages into a concise paragraph (max 150 words).\n"
        "Focus on: games the user is tracking, price targets they have set, deals they were notified about,\n"
        "and any preferences they have expressed. Merge with the existing summary if provided.\n\n"
        f"Existing summary: {existing_summary}\n\n"
        f"Messages to summarize:\n{messages_text}"
    )

    new_summary = gemini_provider.generate_text(prompt)

    _get_client().table("chat_summary").upsert(
        {
            "user_id": user_id,
            "summary": new_summary,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id",
    ).execute()

    ids_to_delete = [m["id"] for m in oldest.data]
    _get_client().table("chat_messages").delete().in_("id", ids_to_delete).execute()
    logger.info("Summarized %d messages for user %s", len(ids_to_delete), user_id)


def force_summarize(user_id: str, gemini_provider) -> str:
    """Summarize ALL messages for a user, store summary, and delete messages. Returns the summary."""
    all_messages = (
        _get_client()
        .table("chat_messages")
        .select("id,role,content")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .execute()
    )
    if not all_messages.data:
        return "No conversation history to summarize."

    summary_result = (
        _get_client().table("chat_summary").select("summary").eq("user_id", user_id).execute()
    )
    existing_summary = summary_result.data[0]["summary"] if summary_result.data else "None"

    messages_text = "\n".join(f"{m['role']}: {m['content']}" for m in all_messages.data)
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

    _get_client().table("chat_summary").upsert(
        {
            "user_id": user_id,
            "summary": new_summary,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id",
    ).execute()

    ids_to_delete = [m["id"] for m in all_messages.data]
    _get_client().table("chat_messages").delete().in_("id", ids_to_delete).execute()
    logger.info("Force-summarized %d messages for user %s", len(ids_to_delete), user_id)
    return new_summary


def clear_memory(user_id: str) -> None:
    """Delete ALL chat messages and summary for a user (full reset)."""
    _get_client().table("chat_messages").delete().eq("user_id", user_id).execute()
    _get_client().table("chat_summary").delete().eq("user_id", user_id).execute()
    logger.info("Cleared all memory for user %s", user_id)
