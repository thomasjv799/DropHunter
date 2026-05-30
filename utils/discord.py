import os

import requests
from dotenv import load_dotenv


def send_deal_alert(
    game_title: str,
    price: float,
    regular_price: float,
    store: str,
    cut: int,
    ai_commentary: str,
) -> None:
    load_dotenv()
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise EnvironmentError("DISCORD_WEBHOOK_URL is not set. Add it to your .env file.")
    message = (
        f"**Deal Alert: {game_title}**\n"
        f"₹{price:.2f} on {store} ({cut}% off, was ₹{regular_price:.2f})\n"
        f"{ai_commentary}"
    )
    response = requests.post(webhook_url, json={"content": message})
    response.raise_for_status()


def send_watch_alert(
    watch_name: str,
    price: float,
    seller: str,
    target_price: float,
    ai_commentary: str,
) -> None:
    load_dotenv()
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise EnvironmentError("DISCORD_WEBHOOK_URL is not set. Add it to your .env file.")
    message = (
        f"**Watch Deal Alert: {watch_name}**\n"
        f"₹{price:.2f} on {seller} (target was ₹{target_price:.2f})\n"
        f"{ai_commentary}"
    )
    response = requests.post(webhook_url, json={"content": message})
    response.raise_for_status()
