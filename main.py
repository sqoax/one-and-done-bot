from flask import Flask
from threading import Thread
import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz
import os
import json

# === Flask Keep-Alive ===
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# === Load environment ===
TOKEN = os.getenv("DISCORD_TOKEN")
REVEAL_CHANNEL_ID = 1390047692163645480  # Your updated channel ID
OWNER_ID = 512106151241056257  # Your Discord user ID

# === Discord bot setup ===
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# === Load/save picks ===
PICKS_FILE = "picks.json"

def load_picks():
    if os.path.exists(PICKS_FILE):
        with open(PICKS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_picks(picks):
    with open(PICKS_FILE, "w") as f:
        json.dump(picks, f, indent=4)

picks = load_picks()

# === Bot Events ===
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    auto_reveal_task.start()

# === Anyone can DM a pick ===
@bot.command()
async def pick(ctx, *, golfer: str):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("📬 Please DM me your pick!")
        return

    now = datetime.now(pytz.timezone('US/Eastern'))
    picks[str(ctx.author.id)] = {
        "name": ctx.author.display_name,
        "pick": golfer,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S %Z")
    }

    save_picks(picks)
    await ctx.send(f"✅ Got it! Your pick '{golfer}' has been locked in.")

# === Only you can trigger test post ===
@bot.command()
async def testpost(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ You're not authorized to use this command.")
        return

    channel = bot.get_channel(REVEAL_CHANNEL_ID)
    if channel:
        await channel.send("📣 This is a test post to confirm the bot can send messages.")
    else:
        await ctx.send("❌ Could not find the reveal channel. Check REVEAL_CHANNEL_ID.")

# === Only you can manually reveal picks ===
@bot.command()
async def revealnow(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ You're not authorized to use this command.")
        return

    channel = bot.get_channel(REVEAL_CHANNEL_ID)
    if not picks:
        await channel.send("⚠️ No picks were submitted this week.")
        return
    output = "**📣 This Week’s Picks:**\n"
    for p in picks.values():
        output += f"- **{p['name']}**: {p['pick']} *(submitted {p['timestamp']})*\n"
    await channel.send(output)
    picks.clear()
    save_picks(picks)

# === Auto reveal every Wednesday at 9:00 PM Eastern ===
@tasks.loop(minutes=1)
async def auto_reveal_task():
    now = datetime.now(pytz.timezone('US/Eastern'))
    if now.strftime('%A') == 'Wednesday' and now.strftime('%H:%M') == '21:00':
        channel = bot.get_channel(REVEAL_CHANNEL_ID)
        if not picks:
            await channel.send("⚠️ No picks were submitted this week.")
            return
        output = "**📣 This Week’s Picks:**\n"
        for p in picks.values():
            output += f"- **{p['name']}**: {p['pick']} *(submitted {p['timestamp']})*\n"
        await channel.send(output)
        picks.clear()
        save_picks(picks)

keep_alive()
bot.run(TOKEN)
