import logging

from ai import get_provider
from db.client import (
    get_games,
    get_last_notified_price,
    insert_price_history,
    log_notification,
)
from utils.discord import send_deal_alert
from utils.itad import get_best_price, get_historical_low

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

    target_price = game.get("target_price")
    if target_price is not None:
        threshold = float(target_price)
        is_deal = price_data["price"] <= threshold
        logger.info(
            "[%s] Target price: ₹%.2f | Current: ₹%.2f | Is deal: %s",
            title, threshold, price_data["price"], is_deal,
        )
    else:
        historical_low = get_historical_low(game["itad_id"])
        if historical_low is None:
            logger.warning("[%s] No ITAD historical low available, skipping.", title)
            return
        is_deal = price_data["price"] <= historical_low
        logger.info(
            "[%s] ITAD historical low: ₹%.2f | Current: ₹%.2f | Is deal: %s",
            title, historical_low, price_data["price"], is_deal,
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
