import asyncio
import logging
import os
from typing import Optional

import discord
from dotenv import load_dotenv

from ai.graph import run_graph

logger = logging.getLogger("drophunter.bot")

_CHANNEL_ID: Optional[int] = None


def _get_channel_id() -> int:
    global _CHANNEL_ID
    if _CHANNEL_ID is None:
        load_dotenv()
        channel_id = os.environ.get("DISCORD_CHANNEL_ID")
        if not channel_id:
            raise EnvironmentError(
                "DISCORD_CHANNEL_ID is not set. Add it to your .env file."
            )
        _CHANNEL_ID = int(channel_id)
    return _CHANNEL_ID


intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    logger.info("DropHunter bot ready as %s", bot.user)
    logger.info("Listening on channel ID: %s", _get_channel_id())


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.channel.id != _get_channel_id():
        return

    user_id = str(message.author.id)
    user_text = message.content
    logger.info("Message from %s: %s", message.author, user_text[:100])

    try:
        async with message.channel.typing():
            reply = await asyncio.to_thread(run_graph, user_id, user_text)
    except Exception as exc:
        logger.error("Unhandled error processing message: %s", exc, exc_info=True)
        reply = (
            f"⚠️ Something went wrong while processing your request.\n"
            f"```\n{type(exc).__name__}: {exc}\n```"
        )

    await message.channel.send(reply[:2000])


def run():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.client").setLevel(logging.INFO)

    load_dotenv()
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise EnvironmentError(
            "DISCORD_BOT_TOKEN is not set. Add it to your .env file."
        )

    logger.info("Starting DropHunter bot...")
    bot.run(token, log_handler=None)
