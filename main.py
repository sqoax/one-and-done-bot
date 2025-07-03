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
WEEKS_FILE = "weeks.json"

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return {}

def save_json(data, filename):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

picks = load_json(PICKS_FILE)
weeks = load_json(WEEKS_FILE)

# === Bot Events ===
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    auto_reveal_task.start()
    update_weeks_task.start()

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

    save_json(picks, PICKS_FILE)
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
    save_json(picks, PICKS_FILE)

# === Show remaining weeks ===
@bot.command()
async def weeksleft(ctx):
    if not weeks:
        await ctx.send("📭 No tournaments remaining.")
        return
    output = "**📅 Remaining Tournaments:**\n"
    for name, purse in weeks.items():
        output += f"- **{name}**: ${purse:,.2f}\n"
    await ctx.send(output)

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
        save_json(picks, PICKS_FILE)

# === Auto remove top tournament every Thursday at 3:00 AM Eastern ===
@tasks.loop(minutes=1)
async def update_weeks_task():
    now = datetime.now(pytz.timezone('US/Eastern'))
    if now.strftime('%A') == 'Thursday' and now.strftime('%H:%M') == '03:00':
        if weeks:
            first_key = next(iter(weeks))
            del weeks[first_key]
            save_json(weeks, WEEKS_FILE)

keep_alive()
bot.run(TOKEN)
