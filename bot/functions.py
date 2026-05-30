import logging

from db.client import (
    add_game as db_add_game,
    add_watch as db_add_watch,
    clear_memory as db_clear_memory,
    force_summarize as db_force_summarize,
    get_games as db_get_games,
    get_recent_deals as db_get_recent_deals,
    get_watches as db_get_watches,
    remove_game as db_remove_game,
    remove_watch as db_remove_watch,
    set_target_price as db_set_target_price,
    set_watch_target as db_set_watch_target,
)
from utils.itad import get_all_prices, get_historical_low, search_game
from utils.watches import fetch_swisstimehouse

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


def get_historical_low_price(title: str) -> str:
    logger.info("get_historical_low_price called: title=%s", title)
    game = search_game(title)
    if game is None:
        return f"Sorry, '{title}' was not found on IsThereAnyDeal."
    low = get_historical_low(game["id"])
    if low is None:
        return f"No historical low data found for **{game['title']}**."
    return f"The all-time historical low for **{game['title']}** is ₹{low:.2f}."


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


def add_watch(url: str, target_price: float = None) -> str:
    logger.info("add_watch called: url=%s, target_price=%s", url, target_price)
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
            "name": "get_historical_low_price",
            "description": "Get the all-time historical low price for a game from IsThereAnyDeal.",
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
    {
        "type": "function",
        "function": {
            "name": "clear_memory",
            "description": "Clear and summarize the conversation history. Use when the user asks to 'clear memory', 'reset conversation', 'start fresh', or similar. This summarizes the key facts and removes old messages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The user's ID (passed automatically).",
                    }
                },
                "required": ["user_id"],
            },
        },
    },
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
                    "url": {
                        "type": "string",
                        "description": "A swisstimehouse.com product page URL.",
                    },
                    "target_price": {
                        "type": "number",
                        "description": "Target alert price in INR.",
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
]


def clear_memory(user_id: str) -> str:
    """Clear memory via tool call."""
    logger.info("clear_memory called for user_id=%s", user_id)
    from ai.gemini_provider import GeminiProvider
    summary = db_force_summarize(user_id, GeminiProvider())
    return f"Memory cleared and summarized. Key facts retained: {summary[:300]}"


_FUNCTION_MAP = {
    "add_game": add_game,
    "remove_game": remove_game,
    "list_games": list_games,
    "get_current_price": get_current_price,
    "get_recent_deals": get_recent_deals,
    "set_target_price": set_target_price,
    "get_historical_low_price": get_historical_low_price,
    "clear_memory": clear_memory,
    "add_watch": add_watch,
    "list_watches": list_watches,
    "get_watch_price": get_watch_price,
    "set_watch_target": set_watch_target,
    "remove_watch": remove_watch,
}


def dispatch(name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments."""
    fn = _FUNCTION_MAP.get(name)
    if fn is None:
        logger.error("Unknown tool requested: %s", name)
        return f"Unknown tool: {name}"
    return fn(**(arguments or {}))
