import logging

from db.client import (
    add_game as db_add_game,
    get_games as db_get_games,
    get_recent_deals as db_get_recent_deals,
    remove_game as db_remove_game,
    set_target_price as db_set_target_price,
)
from utils.itad import get_all_prices, search_game

logger = logging.getLogger("drophunter.functions")


def add_game(title: str, target_price: float = None) -> str:
    logger.info("add_game called: title=%s, target_price=%s", title, target_price)
    game = search_game(title)
    if game is None:
        logger.warning("Game not found on ITAD: %s", title)
        return f"Sorry, '{title}' was not found on IsThereAnyDeal."
    result = db_add_game(game["title"], game["id"], target_price=target_price)
    logger.info("Game upserted in watchlist: %s (id=%s)", game["title"], game["id"])
    if target_price is not None:
        return f"Tracking **{game['title']}**. I'll alert you when it drops below ₹{target_price:.2f}."
    return f"Tracking **{game['title']}**. I'll alert you when a deal drops."


def set_target_price(title: str, target_price: float = None) -> str:
    logger.info("set_target_price called: title=%s, target_price=%s", title, target_price)
    updated = db_set_target_price(title, target_price)
    if not updated:
        return f"**{title}** wasn't found in your watchlist."
    if target_price is None:
        return f"Removed target price for **{title}**. I'll now alert on historical lows."
    return f"Target price for **{title}** set to ₹{target_price:.2f}."


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
    lines = []
    for g in games:
        line = f"• {g['title']}"
        if g.get("target_price") is not None:
            line += f" (target: ₹{g['target_price']:.2f})"
        lines.append(line)
    return f"**Games you're tracking:**\n" + "\n".join(lines)


def get_current_price(title: str) -> str:
    logger.info("get_current_price called: title=%s", title)
    game = search_game(title)
    if game is None:
        logger.warning("Game not found on ITAD: %s", title)
        return f"Sorry, '{title}' was not found on IsThereAnyDeal."
    prices = get_all_prices(game["id"])
    if not prices:
        logger.info("No deals found for %s", game["title"])
        return f"No current deals found for **{game['title']}**."
    
    lines = [f"**{game['title']}** prices:"]
    for p in prices[:10]:
        lines.append(f"• {p['store']}: ₹{p['price']:.2f} ({p['cut']}% off, was ₹{p['regular_price']:.2f})")
    
    logger.info("Fetched %d prices for %s", len(prices), game["title"])
    return "\n".join(lines)


def get_recent_deals() -> str:
    logger.info("get_recent_deals called")
    deals = db_get_recent_deals()
    logger.info("Found %d recent deal(s)", len(deals))
    if not deals:
        return "No recent deals found."
    lines = "\n".join(
        f"• **{d['games']['title']}** — ₹{d['price']:.2f}"
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
            "description": "Add a game to the watchlist to track its price. Optionally set a target price threshold in INR to only alert when the price drops below that amount.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The name of the game to track.",
                    },
                    "target_price": {
                        "type": "number",
                        "description": "Optional price threshold in INR. Only alert when price drops below this amount.",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_target_price",
            "description": "Set or update a custom target price threshold in INR for a tracked game. Pass null to remove the threshold and revert to historical low alerts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The name of the tracked game.",
                    },
                    "target_price": {
                        "type": "number",
                        "description": "Price threshold in INR. Omit or pass null to remove.",
                    },
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
            "parameters": {"type": "object", "properties": {}, "required": []},
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
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

_FUNCTION_MAP = {
    "add_game": add_game,
    "remove_game": remove_game,
    "list_games": list_games,
    "get_current_price": get_current_price,
    "get_recent_deals": get_recent_deals,
    "set_target_price": set_target_price,
}


def dispatch(name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments."""
    fn = _FUNCTION_MAP.get(name)
    if fn is None:
        logger.error("Unknown tool requested: %s", name)
        return f"Unknown tool: {name}"
    return fn(**(arguments or {}))
