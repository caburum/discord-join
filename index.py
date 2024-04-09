import dotenv
from os import environ
import discord
from discord import app_commands
from dateparser import parse
from datetime import datetime
import pytz
import asyncio
from threading import Event

dotenv.load_dotenv()
GUILD_ID = int(environ.get('GUILD_ID'))
CHANNEL_ID = int(environ.get('CHANNEL_ID'))
USER_ID = int(environ.get('USER_ID'))
MOD_IDS = [int(id) for id in environ.get('MOD_IDS').split(',')]
TIMEZONE = pytz.timezone(environ.get('TIMEZONE'))

class MyClient(discord.Client):
	async def on_ready(self):
		print(f'Logged on as {self.user}!')

	# async def on_message(self, message):
	# 	print(f'Message from {message.author}: {message.content}')

intents = discord.Intents.default()
# intents.message_content = True
intents.members = True

client = MyClient(intents=intents)

stop = Event()
latestTarget: datetime | None = None

async def schedule_task(targetTime: datetime):
	global latestTarget

	time_difference = (targetTime - datetime.now()).total_seconds()
	if time_difference > 0:
		await asyncio.sleep(time_difference)
	
	if latestTarget != targetTime: return

	text = f"<@{USER_ID}> you're late"

	channel = client.get_channel(CHANNEL_ID)
	message = await channel.send(text)
	thread = await channel.create_thread(name="late alert", message=message, auto_archive_duration=60)

	for _ in range(500):
		if stop.is_set(): return
		await thread.send(text)
		await asyncio.sleep(1.5)

@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
	if before.channel is None and after.channel and member.id == USER_ID:
		stop.set()

tree = app_commands.CommandTree(client)

@tree.command(
	name="joinalert",
	description="set a time",
	guild=discord.Object(id=GUILD_ID)
)
async def joinalert(interaction: discord.Interaction, time: str):
	if interaction.user.id not in MOD_IDS:
		await interaction.response.send_message("you thought", ephemeral=True)
		return

	settings = {"RELATIVE_BASE": datetime.now(tz=TIMEZONE), "RETURN_AS_TIMEZONE_AWARE": True}

	parsedTime = parse(time, settings=settings)
	print(time, parsedTime)

	if parsedTime is None:
		await interaction.response.send_message("invalid time", ephemeral=True)
		return

	now = datetime.now(tz=TIMEZONE).replace(second=0, microsecond=0) # round to minute

	# assume time without additional info will be in future pm
	if parsedTime.date() == now.date() and 'am' not in time.lower() and parsedTime.hour < 12 and parsedTime.hour < now.hour:
		time = time + ' pm'
		parsedTime = parse(time, settings=settings)
	print('now', datetime.now(tz=TIMEZONE), TIMEZONE, 'target', parsedTime, parsedTime.tzinfo)

	if parsedTime < now:
		await interaction.response.send_message("past time", ephemeral=True)
		return

	member = client.get_guild(GUILD_ID).get_member(USER_ID)

	if not member:
		await interaction.response.send_message("user not found", ephemeral=True)
		return

	if member and member.voice and member.voice.channel:
		await interaction.response.send_message("already in vc", ephemeral=True)
		return

	global latestTarget
	latestTarget = parsedTime

	stop.clear()
	asyncio.ensure_future(schedule_task(parsedTime))

	await interaction.response.send_message(f"{(member.nick if member.nick else member.name) if member else USER_ID} better join <t:{int(parsedTime.timestamp())}:R>")

@tree.command(
	name="cancel",
	description="cancel the alert",
	guild=discord.Object(id=GUILD_ID)
)
async def cancel(interaction: discord.Interaction):
	if interaction.user.id not in MOD_IDS:
		await interaction.response.send_message("you thought", ephemeral=True)
		return

	global latestTarget
	latestTarget = None

	stop.set()
	await interaction.response.send_message("canceled", ephemeral=True)

@client.event
async def on_ready():
	await tree.sync(guild=discord.Object(id=GUILD_ID))
	print("Ready!")

client.run(environ.get('DISCORD_TOKEN'))