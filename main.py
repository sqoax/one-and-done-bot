from flask import Flask
from threading import Thread
import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

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
REVEAL_CHANNEL_ID = 1390047692163645480
OWNER_ID = 512106151241056257

# === Google Sheets Setup ===
GOOGLE_CREDS = json.loads(os.getenv("GOOGLE_CREDS"))
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDS, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key('1_Y7feQqwJhpcnKFmIHu908AepoKHvs_qUWNhcK7WZBQ').worksheet('Sheet1')

# === Discord bot setup ===
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

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

# === Bot Events ===
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    auto_reveal_task.start()
    update_weeks_task.start()

# === DM Picks ===
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

# === Manual Reveal Command ===
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

# === Weeks Remaining ===
@bot.command()
async def weeksleft(ctx):
    if not weeks:
        await ctx.send("📭 No tournaments remaining.")
        return
    output = "**📅 Remaining Tournaments:**\n"
    for name, purse in weeks.items():
        output += f"- **{name}**: ${purse:,.2f}\n"
    await ctx.send(output)

# === Total Earnings ===
@bot.command()
async def totals(ctx):
    hiatt = sheet.acell('O6').value
    caden = sheet.acell('O7').value
    bennett = sheet.acell('O8').value
    await ctx.send(f"""**💰 Current Totals:**  
Hiatt — {hiatt}  
Caden — {caden}  
Bennett — {bennett}""")

# === Allocate 1 Unit Evenly Across Bets ===
@bot.command()
async def allocate(ctx, *, raw_input: str):
    import re

    try:
        # Parse player and odds from input
        lines = raw_input.strip().split('\n')
        bets = []
        for line in lines:
            match = re.match(r'(.+?)\s+(\d+)\s*/\s*1', line.strip())
            if match:
                player = match.group(1).strip()
                odds = int(match.group(2).strip())
                bets.append((player, odds))

        if not bets:
            await ctx.send("⚠️ Couldn’t parse any valid bets. Make sure the format is like: `Player Name 80/1`")
            return

        target_payout = 122.5  # We'll fix payout at $122.50 per player
        stakes = []
        total_stake = 0

        for name, odds in bets:
            stake = target_payout / odds
            total_stake += stake
            stakes.append((name, odds, stake))

        # Normalize to 1 unit total
        normalized = []
        for name, odds, stake in stakes:
            fraction = stake / total_stake
            dollars = fraction * 1.0
            win = dollars * odds
            normalized.append((name, odds, fraction, dollars, win))

        # Format message
        msg = "📊 **1 Unit Allocation**\n\n"
        for name, odds, fraction, stake, win in normalized:
            msg += f"- **{name}** — {fraction:.2f}u (${stake:.2f}) — win ${win:.2f}\n"

        await ctx.send(msg)

    except Exception as e:
        await ctx.send(f"❌ Error calculating allocation: {e}")

# === Current Leader ===
@bot.command()
async def leader(ctx):
    name = sheet.acell('O2').value
    amount = sheet.acell('O3').value
    await ctx.send(f"🏆 {name} is currently winning by {amount}")

# === Current Loser ===
@bot.command()
async def loser(ctx):
    hiatt = sheet.acell('O6').value
    caden = sheet.acell('O7').value
    bennett = sheet.acell('O8').value

    def to_number(val):
        return float(val.replace('$', '').replace(',', ''))

    earnings = {
        "Hiatt": to_number(hiatt),
        "Caden": to_number(caden),
        "Bennett": to_number(bennett)
    }

    loser_name = min(earnings, key=earnings.get)
    loser_amount = f"${earnings[loser_name]:,.2f}"

    await ctx.send(f"🏳️‍🌈 The queerbag in last place is **{loser_name}** with **{loser_amount}**")

# === Gap to 1st Place ===
@bot.command()
async def delta(ctx):
    hiatt = sheet.acell('O6').value
    caden = sheet.acell('O7').value
    bennett = sheet.acell('O8').value

    def to_number(val):
        return float(val.replace('$', '').replace(',', ''))

    earnings = {
        "Hiatt": to_number(hiatt),
        "Caden": to_number(caden),
        "Bennett": to_number(bennett)
    }

    sorted_players = sorted(earnings.items(), key=lambda x: x[1], reverse=True)
    first_name, first_amount = sorted_players[0]

    msg = "📊 **Gap to 1st Place:**\n\n"
    for name, amount in sorted_players:
        if name == first_name:
            msg += f"🥇 {name} — $0.00\n"
        else:
            gap = first_amount - amount
            msg += f"{'🥈' if name == sorted_players[1][0] else '🥉'} {name} — trailing by ${gap:,.2f}\n"

    await ctx.send(msg)

# === Test Post (Owner Only) ===
@bot.command()
async def testpost(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ You're not authorized to use this command.")
        return
    channel = bot.get_channel(REVEAL_CHANNEL_ID)
    if channel:
        await channel.send("📣 This is a test post to confirm the bot can send messages.")
    else:
        await ctx.send("❌ Could not find the reveal channel.")

# === Auto Reveal Loop ===
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

# === Remove First Tournament Weekly ===
@tasks.loop(minutes=1)
async def update_weeks_task():
    now = datetime.now(pytz.timezone('US/Eastern'))
    if now.strftime('%A') == 'Thursday' and now.strftime('%H:%M') == '03:00':
        if weeks:
            first_key = next(iter(weeks))
            del weeks[first_key]
            save_json(weeks, WEEKS_FILE)

# === Launch Bot ===
keep_alive()
bot.run(TOKEN)
