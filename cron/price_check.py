import logging
import sys
from datetime import datetime, timezone
from html import escape

from ai import get_provider
from db.client import (
    get_games,
    get_last_notified_price,
    get_last_watch_notified_price,
    get_user_email,
    get_watches,
    insert_price_history,
    insert_watch_price_history,
    is_user_allowed,
    log_job_run,
    log_notification,
    log_watch_notification,
)
from utils.discord import send_dm
from utils.email import send_email
from utils.itad import get_best_price, get_historical_low
from utils.watches import fetch_swisstimehouse

logger = logging.getLogger("drophunter.cron")


def _commentary(prompt: str) -> str:
    try:
        return get_provider().generate_text(prompt)
    except Exception as exc:
        logger.warning("AI commentary unavailable (%s); sending price alert.", type(exc).__name__)
        return "Your price threshold has been reached."


def _email_alert(user_id: str, subject: str, message: str) -> None:
    try:
        address = get_user_email(user_id)
        if address:
            send_email(
                address, subject, "<p>" + escape(message).replace("\n", "<br>") + "</p>", message
            )
    except Exception as exc:
        logger.warning("Optional email alert failed (%s)", type(exc).__name__)


def process_game(game: dict) -> int | None:
    title = game["title"]
    logger.info("[%s] Fetching price from ITAD...", title)

    price_data = get_best_price(game["itad_id"])
    if price_data is None:
        logger.info("[%s] No price data available, skipping.", title)
        return

    logger.info(
        "[%s] Current: ₹%.2f on %s (%d%% off)",
        title,
        price_data["price"],
        price_data["store"],
        price_data["cut"],
    )

    insert_price_history(
        game_id=game["id"],
        price=price_data["price"],
        regular_price=price_data["regular_price"],
        store=price_data["store"],
    )

    target_price = game.get("target_price")
    # A custom target does not depend on the historical-low API being available.
    historical_low = get_historical_low(game["itad_id"]) if target_price is None else None
    if target_price is not None:
        threshold = float(target_price)
        is_deal = price_data["price"] <= threshold
        logger.info(
            "[%s] Target price: ₹%.2f | Current: ₹%.2f | Is deal: %s",
            title,
            threshold,
            price_data["price"],
            is_deal,
        )
    else:
        if historical_low is None:
            logger.warning("[%s] No ITAD historical low available, skipping.", title)
            return
        is_deal = price_data["price"] <= historical_low
        logger.info(
            "[%s] ITAD historical low: ₹%.2f | Current: ₹%.2f | Is deal: %s",
            title,
            historical_low,
            price_data["price"],
            is_deal,
        )

    if not is_deal:
        return

    last_notified_price = get_last_notified_price(game["id"])
    if last_notified_price is not None and price_data["price"] >= last_notified_price:
        logger.info(
            "[%s] Price ₹%.2f is not lower than last notified ₹%.2f, skipping.",
            title,
            price_data["price"],
            last_notified_price,
        )
        return

    owner = game["user_id"]
    if not is_user_allowed(owner):
        logger.info("[%s] Owner %s no longer permitted, skipping alert.", title, owner)
        return

    logger.info("[%s] Deal detected! Generating AI commentary...", title)
    low_info = f" Historical low: ₹{historical_low}." if historical_low is not None else ""
    commentary = _commentary(
        f"Write a one-sentence buy recommendation for '{title}'. "
        f"Current price: ₹{price_data['price']} on {price_data['store']} "
        f"({price_data['cut']}% off).{low_info}"
    )

    message = (
        f"**Deal Alert: {title}**\n"
        f"₹{price_data['price']:.2f} on {price_data['store']} "
        f"({price_data['cut']}% off, was ₹{price_data['regular_price']:.2f})\n"
        f"{commentary}"
    )
    send_dm(owner, message)
    log_notification(game["id"], price_data["price"])
    _email_alert(owner, f"Deal Alert: {title}", message)
    logger.info("[%s] Deal alert sent!", title)
    return 1


_SWISS_SELLER = "Swiss Time House"


def process_watch(watch: dict) -> int | None:
    name = watch["name"]
    logger.info("[%s] Fetching watch price...", name)

    swiss_price = None
    url = watch.get("swisstimehouse_url")
    if not url:
        logger.warning("[%s] No swisstimehouse_url configured, skipping fetch.", name)
    else:
        fetched = fetch_swisstimehouse(url)
        if fetched is not None:
            swiss_price = fetched["price"]

    insert_watch_price_history(
        watch_id=watch["id"], swisstimehouse_price=swiss_price, myntra_price=None
    )

    # Lowest available price across sources (only swisstimehouse in v1).
    candidates = [(swiss_price, _SWISS_SELLER)]
    available = [(p, s) for p, s in candidates if p is not None]
    if not available:
        logger.info("[%s] No price available this sweep, skipping.", name)
        return

    price, seller = min(available, key=lambda ps: ps[0])
    target = float(watch["target_price"])
    if price > target:
        logger.info("[%s] ₹%.2f above target ₹%.2f, skipping.", name, price, target)
        return

    last_notified = get_last_watch_notified_price(watch["id"])
    if last_notified is not None and price >= last_notified:
        logger.info(
            "[%s] ₹%.2f not lower than last notified ₹%.2f, skipping.",
            name,
            price,
            last_notified,
        )
        return

    owner = watch["user_id"]
    if not is_user_allowed(owner):
        logger.info("[%s] Owner %s no longer permitted, skipping alert.", name, owner)
        return

    logger.info("[%s] Deal! ₹%.2f on %s. Generating commentary...", name, price, seller)
    commentary = _commentary(
        f"Write a one-sentence buy recommendation for the watch '{name}'. "
        f"Current price: ₹{price} on {seller}, below the user's target of ₹{target}."
    )
    message = (
        f"**Watch Deal Alert: {name}**\n"
        f"₹{price:.2f} on {seller} (target was ₹{target:.2f})\n"
        f"{commentary}"
    )
    send_dm(owner, message)
    log_watch_notification(watch["id"], price, seller)
    _email_alert(owner, f"Watch Deal Alert: {name}", message)
    logger.info("[%s] Watch alert sent!", name)
    return 1


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _sweep(job_name, fetch_rows, process_row) -> bool:
    started_at = datetime.now(timezone.utc)
    counts = {"rows_swept": 0, "notifications_sent": 0, "errors": 0}
    errors = []
    try:
        rows = fetch_rows()
        logger.info("%s: checking %d item(s)", job_name, len(rows))
        for row in rows:
            counts["rows_swept"] += 1
            try:
                sent = process_row(row)
                counts["notifications_sent"] += sent if isinstance(sent, int) else 0
            except Exception as exc:
                counts["errors"] += 1
                errors.append(type(exc).__name__)
                logger.error("%s: item failed (%s)", job_name, type(exc).__name__)
    except Exception as exc:
        counts["errors"] += 1
        errors.append(type(exc).__name__)
        logger.error("%s: sweep failed (%s)", job_name, type(exc).__name__)
    try:
        log_job_run(
            job_name=job_name,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status="error" if errors else "ok",
            error_text=", ".join(errors)[:2000] or None,
            counts=counts,
        )
    except Exception as exc:
        logger.error("%s: could not record job run (%s)", job_name, type(exc).__name__)
        return False
    logger.info("%s complete: %s", job_name, counts)
    return not errors


def sweep_games() -> bool:
    return _sweep("drophunter.games", get_games, process_game)


def sweep_watches() -> bool:
    return _sweep("drophunter.watches", get_watches, process_watch)


def run(games: bool = True, watches: bool = True) -> int:
    _configure_logging()
    success = True
    if games:
        success = sweep_games() and success
    if watches:
        success = sweep_watches() and success
    logger.info("Price check run complete.")
    return 0 if success else 1


def _parse_scope(argv: list[str]) -> tuple[bool, bool]:
    """Return (run_games, run_watches). No --games/--watches flag means run both."""
    if "--games" in argv or "--watches" in argv:
        return ("--games" in argv, "--watches" in argv)
    return (True, True)


if __name__ == "__main__":
    run_games, run_watches = _parse_scope(sys.argv[1:])
    sys.exit(run(games=run_games, watches=run_watches))
