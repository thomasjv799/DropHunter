import logging

from db.client import (
    add_game as db_add_game,
)
from db.client import (
    get_games as db_get_games,
)
from db.client import (
    get_recent_deals as db_get_recent_deals,
)
from db.client import (
    remove_game as db_remove_game,
)
from utils.itad import get_best_price, search_game

logger = logging.getLogger("drophunter.functions")


def add_game(title: str) -> str:
    logger.info("add_game called: title=%s", title)
    game = search_game(title)
    if game is None:
        logger.warning("Game not found on ITAD: %s", title)
        return f"Sorry, '{title}' was not found on IsThereAnyDeal."
    db_add_game(game["title"], game["id"])
    logger.info("Game added to watchlist: %s (id=%s)", game["title"], game["id"])
    return f"Now tracking **{game['title']}**. I'll alert you when a deal drops."


def remove_game(title: str) -> str:
    logger.info("remove_game called: title=%s", title)
    removed = db_remove_game(title)
    if removed:
        logger.info("Game removed: %s", title)
        return f"No longer tracking **{title}**."
    logger.warning("Game not in watchlist: %s", title)
    return f"**{title}** wasn't in your watchlist."


def list_games() -> str:
    logger.info("list_games called")
    games = db_get_games()
    logger.info("Found %d game(s) in watchlist", len(games))
    if not games:
        return "Your watchlist is empty. Try 'track <game name>' to add a game."
    lines = "\n".join(f"• {g['title']}" for g in games)
    return f"**Games you're tracking:**\n{lines}"


def get_current_price(title: str) -> str:
    logger.info("get_current_price called: title=%s", title)
    game = search_game(title)
    if game is None:
        logger.warning("Game not found on ITAD: %s", title)
        return f"Sorry, '{title}' was not found on IsThereAnyDeal."
    price_data = get_best_price(game["id"])
    if price_data is None:
        logger.info("No deals found for %s", game["title"])
        return f"No current deals found for **{game['title']}**."
    logger.info(
        "Best price for %s: $%.2f on %s (%d%% off)",
        game["title"],
        price_data["price"],
        price_data["store"],
        price_data["cut"],
    )
    return (
        f"**{game['title']}** — best price: ${price_data['price']:.2f} on {price_data['store']} "
        f"({price_data['cut']}% off, was ${price_data['regular_price']:.2f})"
    )


def get_recent_deals() -> str:
    logger.info("get_recent_deals called")
    deals = db_get_recent_deals()
    logger.info("Found %d recent deal(s)", len(deals))
    if not deals:
        return "No recent deals found."
    lines = "\n".join(
        f"• **{d['games']['title']}** — ${d['price']:.2f}"
        f" (alerted {d['notified_at'][:10] if d['notified_at'] else 'unknown date'})"
        for d in deals
    )
    return f"**Recent deals I found:**\n{lines}"


# Tool definitions in OpenAI function-calling format
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_game",
            "description": "Add a game to the watchlist to track its price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The name of the game to track.",
                    }
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_game",
            "description": "Remove a game from the watchlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The name of the game to remove.",
                    }
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_games",
            "description": "List all games currently on the watchlist.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_price",
            "description": "Get the current best price for a game across all stores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The name of the game to look up.",
                    }
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_deals",
            "description": "Show recent deal alerts that were sent.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_FUNCTION_MAP = {
    "add_game": add_game,
    "remove_game": remove_game,
    "list_games": list_games,
    "get_current_price": get_current_price,
    "get_recent_deals": get_recent_deals,
}


def dispatch(name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments."""
    fn = _FUNCTION_MAP.get(name)
    if fn is None:
        logger.error("Unknown tool requested: %s", name)
        return f"Unknown tool: {name}"
    return fn(**(arguments or {}))
