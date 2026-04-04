import logging
import os
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


def add_game(title: str, itad_id: str) -> dict:
    logger.info("Adding game: %s (itad_id=%s)", title, itad_id)
    result = (
        _get_client()
        .table("games")
        .insert({"title": title, "itad_id": itad_id})
        .execute()
    )
    if not result.data:
        raise RuntimeError(f"Insert into 'games' returned no data: {result}")
    logger.info("Game added successfully: %s", title)
    return result.data[0]


def remove_game(title: str) -> bool:
    logger.info("Removing game: %s", title)
    result = (
        _get_client().table("games").delete().ilike("title", title).execute()
    )
    removed = len(result.data) > 0
    logger.info("Game removed: %s (found=%s)", title, removed)
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
