from flask import Flask
from threading import Thread
import os, json, logging
from datetime import datetime
import pytz

import discord
from discord.ext import commands, tasks

import gspread
from oauth2client.service_account import ServiceAccountCredentials

logging.basicConfig(level=logging.INFO)

# === Flask Keep-Alive ===
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

# === Load environment ===
TOKEN = os.getenv("DISCORD_TOKEN") or ""
REVEAL_CHANNEL_ID = 1390047692163645480
OWNER_ID = 512106151241056257

if not TOKEN.strip():
    raise RuntimeError("DISCORD_TOKEN is empty, set it in Render env vars.")

# === Lazy Google Sheets helpers ===
def get_sheet():
    google_creds = os.getenv("GOOGLE_CREDS")
    if not google_creds:
        raise RuntimeError("GOOGLE_CREDS is missing.")
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(google_creds), scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1_Y7feQqwJhpcnKFmIHu908AepoKHvs_qUWNhcK7WZBQ").worksheet("Sheet1")

# === Discord bot setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# === Load/save picks and weeks ===
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

# === Commands ===
@bot.command()
async def pick(ctx, *, golfer: str):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("📬 Please DM me your pick!")
        return
    now = datetime.now(pytz.timezone("US/Eastern"))
    picks[str(ctx.author.id)] = {
        "name": ctx.author.display_name,
        "pick": golfer,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }
    save_json(picks, PICKS_FILE)
    await ctx.send(f"✅ Got it, your pick '{golfer}' is locked in.")
    general_channel = discord.utils.get(bot.get_all_channels(), name="general")
    if general_channel:
        await general_channel.send(f"📝 **{ctx.author.display_name}** just submitted a pick!")

@bot.command(name="help")
async def _help(ctx):
    await ctx.send(
        "🛠️ **Commands**\n"
        "📬 `!pick [Golfer]` DM only\n"
        "📌 `!mypick`\n"
        "📈 `!pvi [odds] [purse] [earnings]`\n"
        "💸 `!allocate`\n"
        "📊 `!totals`  🏆 `!leader`  🏳 `!loser`  📈 `!delta`\n"
        "📣 `!revealnow`, `!submits`, `!testpost`  owner only"
    )

@bot.command()
async def totals(ctx):
    try:
        sheet = get_sheet()
        hiatt = sheet.acell("O6").value
        caden = sheet.acell("O7").value
        bennett = sheet.acell("O8").value
        await ctx.send(f"**💰 Current Totals:**\nHiatt — {hiatt}\nCaden — {caden}\nBennett — {bennett}")
    except Exception as e:
        await ctx.send(f"❌ Could not read totals, {e}")

# ... keep your other commands unchanged, but consider cleaning up `loser` text

@tasks.loop(minutes=1)
async def dm_reminder_task():
    now = datetime.now(pytz.timezone("US/Eastern"))
    if now.strftime("%A") == "Wednesday" and now.strftime("%H:%M") == "18:00":
        guild = discord.utils.get(bot.guilds)
        if not guild:
            return
        for member in guild.members:
            if member.bot:
                continue
            try:
                await member.send("⏰ Heads up, picks due by **9 PM tonight**. Use `!pick Your Golfer`.")
            except:
                pass

@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user} | Guilds: {[g.name for g in bot.guilds]}")
    auto_reveal_task.start()
    update_weeks_task.start()
    dm_reminder_task.start()

# unchanged: auto_reveal_task, update_weeks_task, pvi, allocate, mypick, leader, loser, submits, revealnow, testpost

# === Launch Bot ===
keep_alive()           # if using a Web Service for UptimeRobot
bot.run(TOKEN)
