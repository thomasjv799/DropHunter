import os

import requests
from dotenv import load_dotenv

_DISCORD_API = "https://discord.com/api/v10"


def send_dm(user_id: str, message: str) -> None:
    """DM a user via the bot token: open (or fetch) the DM channel, then post."""
    load_dotenv()
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise EnvironmentError("DISCORD_BOT_TOKEN is not set. Add it to your .env file.")
    headers = {"Authorization": f"Bot {token}"}
    open_resp = requests.post(
        f"{_DISCORD_API}/users/@me/channels", headers=headers, json={"recipient_id": user_id}
    )
    open_resp.raise_for_status()
    channel_id = open_resp.json()["id"]
    msg_resp = requests.post(
        f"{_DISCORD_API}/channels/{channel_id}/messages", headers=headers, json={"content": message}
    )
    msg_resp.raise_for_status()
