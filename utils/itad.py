import logging
import os
from typing import Optional

import requests
from dotenv import load_dotenv

_BASE_URL = "https://api.isthereanydeal.com"

logger = logging.getLogger("drophunter.itad")


def _api_key() -> str:
    load_dotenv()
    return os.environ["ITAD_API_KEY"]


def search_game(title: str) -> Optional[dict]:
    """Search ITAD for a game by title. Returns the first match or None."""
    logger.info("Searching ITAD for: %s", title)
    response = requests.get(
        f"{_BASE_URL}/games/search/v1",
        params={"title": title, "key": _api_key()},
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        logger.info("No results found for: %s", title)
        return None
    logger.info(
        "Found: %s (id=%s)", results[0].get("title"), results[0].get("id")
    )
    return results[0]


def get_best_price(itad_id: str) -> Optional[dict]:
    """
    Fetch current best price across all stores for a given ITAD game ID.
    Returns dict with keys: price, regular_price, store, cut — or None.
    """
    logger.info("Fetching prices for ITAD id: %s", itad_id)
    response = requests.post(
        f"{_BASE_URL}/games/prices/v3",
        params={"key": _api_key(), "country": "US"},
        json=[itad_id],
    )
    response.raise_for_status()
    data = response.json()
    if not data or not data[0].get("deals"):
        logger.info("No deals found for: %s", itad_id)
        return None
    deals = data[0]["deals"]
    best = min(deals, key=lambda d: d["price"]["amount"])
    result = {
        "price": best["price"]["amount"],
        "regular_price": best["regular"]["amount"],
        "store": best["shop"]["name"],
        "cut": best["cut"],
    }
    logger.info(
        "Best price: $%.2f on %s (%d%% off)",
        result["price"],
        result["store"],
        result["cut"],
    )
    return result
