import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Iterable, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to load %s, using default.", path)
        return default


def save_json(path: Path, data) -> None:
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        logger.exception("Failed to persist data to %s", path)


JAILED_PATH = Path("jailed.json")
intents = discord.Intents.default()
intents.members = True
intents.voice_states = True

client = commands.Bot(command_prefix="!", intents=intents)
tree = client.tree

GUILD_ID = int(require_env("GUILD_ID"))
ABUSE_CHANNEL1 = int(require_env("ABUSE_CHANNEL1"))
ABUSE_CHANNEL2 = int(require_env("ABUSE_CHANNEL2"))
OLLAMA_URL = require_env("OLLAMA_URL")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "wizard-vicuna-uncensored:30b")

server = discord.Object(id=GUILD_ID)
jailed: set[int] = set(load_json(JAILED_PATH, []))
http_session: Optional[aiohttp.ClientSession] = None


async def get_http_session() -> aiohttp.ClientSession:
    global http_session
    if http_session is None or http_session.closed:
        http_session = aiohttp.ClientSession()
    return http_session


@client.event
async def on_ready():
    await tree.sync(guild=server)
    logger.info("Logged in as %s", client.user)


@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if after.channel and member.id in jailed and after.channel.id != ABUSE_CHANNEL2:
        gulag_channel = client.get_channel(ABUSE_CHANNEL2)
        if gulag_channel and isinstance(gulag_channel, discord.VoiceChannel):
            try:
                await member.move_to(gulag_channel)
            except discord.DiscordException:
                logger.exception("Failed to return %s to gulag", member)


async def post_prompt(prompt: str) -> str:
    session = await get_http_session()
    data: Dict[str, object] = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    try:
        async with session.post(OLLAMA_URL, json=data) as response:
            if response.status == 200:
                body = await response.json()
                return body.get("response", "")
            logger.warning("Model service returned status %s", response.status)
    except aiohttp.ClientError:
        logger.exception("Failed to reach model service")
    raise RuntimeError("Failed to get a response from the API.")


def ensure_voice_target(member: discord.Member) -> Optional[discord.VoiceChannel]:
    if not member.voice:
        return None
    return member.voice.channel


async def move_member_between(member: discord.Member, channels: Iterable[discord.VoiceChannel], delay: float = 0.15) -> bool:
    for channel in channels:
        try:
            await member.move_to(channel)
        except discord.DiscordException:
            logger.exception("Failed to move %s", member)
            return False
        await asyncio.sleep(delay)
    return True


@tree.context_menu(name="Answer", guild=server)
async def answer(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer()
    try:
        reply = await post_prompt(message.content)
    except RuntimeError as exc:
        await interaction.followup.send(str(exc))
    else:
        await interaction.followup.send(reply)


def has_move_permissions(user: discord.Member) -> bool:
    return bool(user.guild_permissions.move_members)


@tree.context_menu(name="Abuse", guild=server)
async def wakeup(interaction: discord.Interaction, member: discord.Member):
    if not has_move_permissions(interaction.user):
        await interaction.response.send_message("You do not have permission to move members.", ephemeral=True)
        return

    targetchannel1 = client.get_channel(ABUSE_CHANNEL1)
    targetchannel2 = client.get_channel(ABUSE_CHANNEL2)
    originchannel = ensure_voice_target(member)

    if not all(isinstance(ch, discord.VoiceChannel) for ch in (targetchannel1, targetchannel2)) or originchannel is None:
        await interaction.response.send_message("Target member is not in a voice channel or destinations are invalid.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    pattern = [targetchannel1, targetchannel2] * 4
    if await move_member_between(member, pattern):
        try:
            await member.move_to(originchannel)
        except discord.DiscordException:
            logger.exception("Failed to return %s to origin channel", member)
            await interaction.followup.send(f"Failed to return {member.display_name} to the original channel.", ephemeral=True)
            return
        await interaction.followup.send(f"Woke up {member.display_name}!", ephemeral=True)
    else:
        await interaction.followup.send(f"Failed to move {member.display_name}.", ephemeral=True)


def persist_jailed():
    save_json(JAILED_PATH, list(jailed))


@tree.context_menu(name="Send to gulag", guild=server)
async def arrest(interaction: discord.Interaction, member: discord.Member):
    channel = discord.utils.get(member.guild.text_channels, name='bot-commands')
    if not has_move_permissions(interaction.user):
        if channel:
            await channel.send(f'{interaction.user.mention} has no permission to send people to gulag.')
        else:
            await interaction.response.send_message("You lack permissions to move members.", ephemeral=True)
        return

    gulag = client.get_channel(ABUSE_CHANNEL2)
    if not isinstance(gulag, discord.VoiceChannel):
        await interaction.response.send_message("Gulag channel is not configured correctly.", ephemeral=True)
        return

    if member.voice:
        try:
            await member.move_to(gulag)
        except discord.DiscordException:
            logger.exception("Failed to move %s to gulag", member)
            await interaction.response.send_message("Could not move member to gulag.", ephemeral=True)
            return
        jailed.add(member.id)
        persist_jailed()
        if channel:
            await channel.send(f'{member.mention} has been sent to gulag. ')
        else:
            await interaction.response.send_message("Member sent to gulag.", ephemeral=True)
    else:
        jailed.add(member.id)
        persist_jailed()
        message = f'{member.mention} is not present. Will be sent to gulag once in reach.'
        if channel:
            await channel.send(message)
        else:
            await interaction.response.send_message(message, ephemeral=True)


@tree.context_menu(name="Release from gulag", guild=server)
async def release(interaction: discord.Interaction, member: discord.Member):
    channel = discord.utils.get(member.guild.text_channels, name='bot-commands')
    if not has_move_permissions(interaction.user):
        if channel:
            await channel.send(f'{interaction.user.mention} has no permission to release people from gulag.')
        else:
            await interaction.response.send_message("You lack permissions to release members.", ephemeral=True)
        return

    if member.id in jailed:
        jailed.remove(member.id)
        persist_jailed()
        message = f'{member.mention} has been released from gulag. '
    else:
        message = "This user is not arrested."

    if channel:
        await channel.send(message)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@tree.command(name="respond", description="Process a message", guild=server)
async def respond(interaction: discord.Interaction, input_text: str):
    await interaction.response.defer()
    try:
        reply = await post_prompt(input_text)
    except RuntimeError as exc:
        await interaction.followup.send(str(exc))
    else:
        await interaction.followup.send(reply)


@tree.command(name="join", description="Join the user's voice channel", guild=server)
async def join(interaction: discord.Interaction):
    voice_state = interaction.user.voice
    if voice_state is None or voice_state.channel is None:
        await interaction.response.send_message("You are not connected to a voice channel.", ephemeral=True)
        return

    channel = voice_state.channel
    voice_client = interaction.guild.voice_client
    try:
        if voice_client and voice_client.channel != channel:
            await voice_client.disconnect()
        if interaction.guild.voice_client is None:
            await channel.connect()
    except discord.DiscordException:
        logger.exception("Failed to join voice channel")
        await interaction.response.send_message("Unable to join the voice channel.", ephemeral=True)
        return

    await interaction.response.send_message(f"Joined {channel.name}")


@tree.command(name='leave', description='Leave the voice channel.', guild=server)
async def leave(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        await interaction.response.send_message("Not connected to any voice channel.", ephemeral=True)
        return

    try:
        await voice_client.disconnect()
    except discord.DiscordException:
        logger.exception("Failed to disconnect from voice channel")
        await interaction.response.send_message("Failed to leave the voice channel.", ephemeral=True)
        return

    await interaction.response.send_message("Left the voice channel.")


async def close_http_session():
    if http_session and not http_session.closed:
        await http_session.close()


async def main():
    try:
        await client.start(require_env('DISCORD_TOKEN'))
    finally:
        await close_http_session()


asyncio.run(main())


