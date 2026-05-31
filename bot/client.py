import asyncio
import logging
import os

import discord
from discord import app_commands
from dotenv import load_dotenv

from ai.graph import run_graph

logger = logging.getLogger("drophunter.bot")


def _is_owner(user_id: str) -> bool:
    load_dotenv()
    return user_id == os.environ.get("OWNER_ID")


intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


@bot.event
async def on_ready():
    logger.info("DropHunter bot ready as %s", bot.user)
    try:
        synced = await tree.sync()
        logger.info("Synced %d slash command(s)", len(synced))
    except Exception as exc:
        logger.error("Failed to sync slash commands: %s", exc)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return  # DM-only

    from db.client import is_user_allowed

    user_id = str(message.author.id)
    if not await asyncio.to_thread(is_user_allowed, user_id):
        await message.channel.send("Sorry, you're not authorized to use this bot.")
        logger.info("Rejected unauthorized user %s", user_id)
        return

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


@tree.command(name="clearmemory", description="Summarize and clear your conversation history to reduce hallucinations")
async def clearmemory(interaction: discord.Interaction):
    """Summarize all chat history into key facts and clear raw messages."""
    await interaction.response.defer(thinking=True)
    user_id = str(interaction.user.id)

    try:
        from ai.gemini_provider import GeminiProvider
        from db.client import force_summarize

        summary = await asyncio.to_thread(force_summarize, user_id, GeminiProvider())
        await interaction.followup.send(
            f"✅ **Memory cleared and summarized!**\n\n"
            f"Your conversation history has been condensed into key facts. "
            f"The bot will remember important details (tracked games, target prices) "
            f"but forget the raw conversation.\n\n"
            f"**Summary saved:**\n> {summary[:500]}"
        )
    except Exception as exc:
        logger.error("Failed to clear memory for %s: %s", user_id, exc, exc_info=True)
        await interaction.followup.send(
            f"⚠️ Failed to clear memory.\n```\n{type(exc).__name__}: {exc}\n```"
        )


@tree.command(name="resetmemory", description="Completely wipe your conversation history (full reset)")
async def resetmemory(interaction: discord.Interaction):
    """Delete ALL chat messages and summary — complete fresh start."""
    await interaction.response.defer(thinking=True)
    user_id = str(interaction.user.id)

    try:
        from db.client import clear_memory

        await asyncio.to_thread(clear_memory, user_id)
        await interaction.followup.send(
            "🗑️ **Memory fully reset!**\n\n"
            "All your conversation history and summaries have been deleted. "
            "The bot is starting fresh with no memory of previous conversations."
        )
    except Exception as exc:
        logger.error("Failed to reset memory for %s: %s", user_id, exc, exc_info=True)
        await interaction.followup.send(
            f"⚠️ Failed to reset memory.\n```\n{type(exc).__name__}: {exc}\n```"
        )


@tree.command(name="allow", description="(Owner) Permit a user to use the bot")
@app_commands.describe(user="The user to permit")
async def allow(interaction: discord.Interaction, user: discord.User):
    if not _is_owner(str(interaction.user.id)):
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    from db.client import add_allowed_user
    await asyncio.to_thread(add_allowed_user, str(user.id), str(interaction.user.id))
    await interaction.response.send_message(f"✅ {user.mention} is now permitted.", ephemeral=True)


@tree.command(name="revoke", description="(Owner) Remove a user's access")
@app_commands.describe(user="The user to revoke")
async def revoke(interaction: discord.Interaction, user: discord.User):
    if not _is_owner(str(interaction.user.id)):
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    from db.client import remove_allowed_user
    removed = await asyncio.to_thread(remove_allowed_user, str(user.id))
    msg = f"🗑️ Revoked {user.mention}." if removed else f"{user.mention} wasn't permitted."
    await interaction.response.send_message(msg, ephemeral=True)


@tree.command(name="listusers", description="(Owner) List permitted users")
async def listusers(interaction: discord.Interaction):
    if not _is_owner(str(interaction.user.id)):
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    from db.client import list_allowed_users
    rows = await asyncio.to_thread(list_allowed_users)
    if not rows:
        await interaction.response.send_message(
            "No permitted users yet (owner always allowed).", ephemeral=True
        )
        return
    lines = "\n".join(f"• <@{r['user_id']}>" for r in rows)
    await interaction.response.send_message(f"**Permitted users:**\n{lines}", ephemeral=True)


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
