import logging
import os
import traceback
from typing import Optional

import discord
from dotenv import load_dotenv

from ai import get_provider
from bot.functions import TOOLS, dispatch

logger = logging.getLogger("drophunter.bot")

_CHANNEL_ID: Optional[int] = None

_SYSTEM_PROMPT = (
    "You are DropHunter, a personal game deal assistant. "
    "When the user asks you to track, untrack, list games, check prices, or see recent deals, "
    "use the available tools. For anything else, respond helpfully in plain text."
)


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

    user_text = message.content
    logger.info(
        "Message from %s: %s",
        message.author,
        user_text[:100],
    )

    try:
        provider = get_provider()
    except Exception as e:
        logger.error("Failed to initialize AI provider: %s", e)
        await message.channel.send(
            "⚠️ AI provider error — check your API key and AI_PROVIDER setting."
        )
        return

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    try:
        async with message.channel.typing():
            # Step 1: Ask AI (may return tool calls or direct text)
            logger.info("Sending to AI provider...")
            result = provider.chat_with_tools(messages=messages, tools=TOOLS)
            logger.info("AI response type: %s", "tool_calls" if "tool_calls" in result else "text")

            if "tool_calls" in result:
                tool_responses = []
                for tc in result["tool_calls"]:
                    tool_name = tc["name"]
                    tool_args = tc.get("arguments") or {}
                    logger.info("Executing tool: %s(%s)", tool_name, tool_args)

                    try:
                        tool_result = dispatch(tool_name, tool_args)
                        logger.info("Tool %s returned: %s", tool_name, tool_result[:200])
                        tool_responses.append(tool_result)
                    except Exception as e:
                        error_msg = f"Error in {tool_name}: {e}"
                        logger.error(error_msg, exc_info=True)
                        tool_responses.append(f"⚠️ {error_msg}")

                # Step 2: Feed tool results back to AI for a natural summary
                messages.append({"role": "assistant", "content": str(result)})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Tool results: {'; '.join(tool_responses)}",
                    }
                )
                logger.info("Requesting AI summary of tool results...")
                final = provider.chat_with_tools(messages=messages, tools=[])
                reply = final.get("text", "\n".join(tool_responses))
            else:
                reply = result.get("text", "I'm not sure how to help with that.")

            logger.info("Reply: %s", reply[:200])

    except Exception as e:
        logger.error("Unhandled error processing message: %s", e, exc_info=True)
        reply = (
            f"⚠️ Something went wrong while processing your request.\n"
            f"```\n{type(e).__name__}: {e}\n```"
        )

    await message.channel.send(reply[:2000])  # Discord 2000 char limit


def run():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Reduce noise from discord.py internals
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
