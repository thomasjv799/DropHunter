import logging

from ai import get_provider
from db.client import (
    get_games,
    get_historical_low,
    insert_price_history,
    log_notification,
    was_recently_notified,
)
from utils.discord import send_deal_alert
from utils.itad import get_best_price

logger = logging.getLogger("drophunter.cron")


def process_game(game: dict) -> None:
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

    historical_low = get_historical_low(game["id"])
    if historical_low is None:
        logger.warning(
            "[%s] Historical low returned None after insert, skipping.", title
        )
        return

    is_deal = price_data["price"] <= historical_low
    logger.info(
        "[%s] Historical low: ₹%.2f | Is deal: %s",
        title,
        historical_low,
        is_deal,
    )

    if not is_deal:
        return

    if was_recently_notified(game["id"]):
        logger.info("[%s] Already notified recently, skipping.", title)
        return

    logger.info("[%s] Deal detected! Generating AI commentary...", title)
    provider = get_provider()
    commentary = provider.generate_text(
        f"Write a one-sentence buy recommendation for '{title}'. "
        f"Current price: ₹{price_data['price']} on {price_data['store']} "
        f"({price_data['cut']}% off). Historical low: ₹{historical_low}."
    )

    send_deal_alert(
        game_title=title,
        price=price_data["price"],
        regular_price=price_data["regular_price"],
        store=price_data["store"],
        cut=price_data["cut"],
        ai_commentary=commentary,
    )
    log_notification(game["id"], price_data["price"])
    logger.info("[%s] Deal alert sent!", title)


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    games = get_games()
    logger.info("Checking prices for %d game(s)...", len(games))
    for game in games:
        try:
            process_game(game)
        except Exception as exc:
            logger.error("[%s] ERROR: %s", game["title"], exc, exc_info=True)
    logger.info("Price check run complete.")


if __name__ == "__main__":
    run()
