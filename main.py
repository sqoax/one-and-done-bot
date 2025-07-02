from flask import Flask
from threading import Thread
import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz
import os  # <-- ✅ New: to load the token from environment

# Flask server to keep Replit/Render alive
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ✅ Securely load Discord bot token from environment variable
TOKEN = os.getenv("DISCORD_TOKEN")
REVEAL_CHANNEL_ID = 1390047692163645480  # Replace with your channel ID

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

picks = {}

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    auto_reveal_task.start()

@bot.command()
async def pick(ctx, *, golfer: str):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("📬 Please DM me your pick!")
        return

    now = datetime.now(pytz.timezone('US/Eastern'))
    picks[ctx.author.id] = {
        "name": ctx.author.display_name,
        "pick": golfer,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S %Z")
    }

    await ctx.send(f"✅ Got it! Your pick '{golfer}' has been locked in.")

@tasks.loop(minutes=1)
async def auto_reveal_task():
    now = datetime.now(pytz.timezone('US/Eastern'))
    if now.strftime('%A') == 'Wednesday' and now.strftime('%H:%M') == '20:00':
        channel = bot.get_channel(REVEAL_CHANNEL_ID)
        if not picks:
            await channel.send("⚠️ No picks were submitted this week.")
            return
        output = "**📣 This Week’s Picks:**\n"
        for p in picks.values():
            output += f"- **{p['name']}**: {p['pick']} *(submitted {p['timestamp']})*\n"
        await channel.send(output)
        picks.clear()

keep_alive()
bot.run(TOKEN)
