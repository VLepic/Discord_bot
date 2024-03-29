import discord
from discord import app_commands
import os
import aiohttp
import asyncio




class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commands = []
    async def on_ready(self):
        await tree.sync(guild = server)
        print('Logged in as', self.user)


jailed = []
client = MyClient(intents = discord.Intents.default())
tree = app_commands.CommandTree(client)
server = discord.Object(id=int(os.environ.get('GUILD_ID', '735570517657911318')))

@client.event
async def on_voice_state_update(member, before, after):
    if after.channel is not None:
        if member in jailed and after.channel.id != int(os.environ.get('ABUSE_CHANNEL2', '1100472522270593124')):
            await member.move_to(client.get_channel(int(os.environ.get('ABUSE_CHANNEL2', '1100472522270593124'))))



@tree.context_menu(name="Answer", guild=server)
async def answer(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer()
    await ans(interaction, message)
async def ans(interaction: discord.Interaction, message: discord.Message):
    url = os.environ.get('OLLAMA_URL', '')
    data = {
        "model": os.environ.get('OLLAMA_MODEL', 'wizard-vicuna-uncensored:30b'),
        "prompt": message.content,
        "stream": False
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            if response.status == 200:
                response_json = await response.json()
                await interaction.followup.send(response_json['response'])
            else:
                await interaction.followup.send("Failed to get a response from the API.")

@tree.context_menu(name="Abuse", guild=server)
async def wakeup(interaction: discord.Interaction, member: discord.Member):

    targetchannel1 = client.get_channel(int(os.environ.get('ABUSE_CHANNEL1', '1100472301281091626')))
    targetchannel2 = client.get_channel(int(os.environ.get('ABUSE_CHANNEL2', '1100472522270593124')))
    originchannel = member.voice.channel

    await interaction.response.defer(ephemeral=True)

    for _ in range(4):
        try:
            await member.move_to(targetchannel1)
            await asyncio.sleep(0.15)
            await member.move_to(targetchannel2)
            await asyncio.sleep(0.15)
        except discord.errors.HTTPException:
            await interaction.followup.send(f"Failed to move {member.display_name}.", ephemeral=True)
            return

    await member.move_to(originchannel)
    await interaction.followup.send(f"Woke up {member.display_name}!", ephemeral=True)

@tree.context_menu(name="Send to gulag", guild=server)
async def arrest(interaction: discord.Interaction, member: discord.Member):
    channel = discord.utils.get(member.guild.text_channels, name='bot-commands')
    if interaction.user.guild_permissions.move_members:
        gulag = client.get_channel(int(os.environ.get('ABUSE_CHANNEL2', '1100472522270593124')))
        if member.voice:
            await member.move_to(gulag)
            jailed.append(member)
            if channel:
                await channel.send(f'{member.mention} has been sent to gulag. ')
                return
        else:
            await channel.send(f'{member.mention} is not present. Will be sent to gulag once in reach.')
            jailed.append(member)
            return
    else:
        await channel.send(f'{interaction.user.mention} has no permission to send people to gulag.')


@tree.context_menu(name="Release from gulag", guild=server)
async def release(interaction: discord.Interaction, member: discord.Member):
    channel = discord.utils.get(member.guild.text_channels, name='bot-commands')
    if interaction.user.guild_permissions.move_members:
        if member in jailed:
            jailed.remove(member)
            if channel:
                await channel.send(f'{member.mention} has been released from gulag. ')
        else:
            await channel.send("This user is not arrested.")
    else:
        await channel.send(f'{interaction.user.mention} has no permission to release people from gulag.')


@tree.command(name="respond", description="Process a message", guild=server)
async def respond(interaction: discord.Interaction, input_text: str):
    await interaction.response.defer()
    await ans_with_string_input(interaction, input_text)

async def ans_with_string_input(interaction: discord.Interaction, input_text: str):
    url = os.environ.get('OLLAMA_URL')
    data = {
        "model": os.environ.get('OLLAMA_MODEL', 'wizard-vicuna-uncensored:30b'),
        "prompt": input_text,
        "stream": False
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            if response.status == 200:
                response_json = await response.json()
                await interaction.followup.send(response_json['response'])
            else:
                await interaction.followup.send("Failed to get a response from the API.")

@tree.command(name="join", description="Process a message", guild=server)
async def join(interaction: discord.Interaction):
    if interaction.user.voice is None:
        await interaction.response.send_message("You are not connected to a voice channel.", ephemeral=True)
        return
    channel = interaction.user.voice.channel

    await channel.connect()

    await interaction.response.send_message(f"Joined {channel.name}")

@tree.command(name='leave', description='Leave the voice channel.', guild=server)
async def leave(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        return



    await voice_client.disconnect()
    await interaction.response.send_message("Left the voice channel.")

client.run(os.environ.get('DISCORD_TOKEN'))


