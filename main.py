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
intents.members = True  # Enables access to guild members

bot = commands.Bot(command_prefix='!', intents=intents)# === Load/save picks and weeks ===
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

# === DM Picks ===

@bot.command()
async def pick(ctx, *, golfer: str):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("📬 Please DM me your pick!")
        return

    # Warn about 2-event week
    if ',' not in golfer and ' and ' not in golfer.lower():
        await ctx.send("⚠️ If this is a 2-event week, remember to include **both picks in one message**, like: `!pick Golfer1 and Golfer2`")

    now = datetime.now(pytz.timezone('US/Eastern'))
    picks[str(ctx.author.id)] = {
        "name": ctx.author.display_name,
        "pick": golfer,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S %Z")
    }
    save_json(picks, PICKS_FILE)
    await ctx.send(f"✅ Got it! Your pick '{golfer}' has been locked in.")

    # Send public message to a general channel
    general_channel = discord.utils.get(bot.get_all_channels(), name="general")
    if general_channel:
        await general_channel.send(f"📝 **{ctx.author.display_name}** just submitted a pick!")

@bot.command()
async def commands(ctx):
    await ctx.send("""🛠️ **Available Commands**

📬 `!pick [Golfer]` — *(DM only)* Submit your weekly pick  
📌 `!mypick` — Show your submitted pick and timestamp  
📈 `!pvi [odds] [purse] [earnings]` — Calculate Performance Value Index  
💸 `!allocate` — Calculate even unit allocation across bets  

📊 `!totals` — Show current total earnings  
🏆 `!leader` — Show who’s in 1st place  
🏳️ `!loser` — Show who’s in last  
📈 `!delta` — Show gap to 1st  

📣 `!revealnow` — *(Owner only)* Reveal all picks  
📬 `!submits` — *(Owner only)* Show submission times  
🧪 `!testpost` — *(Owner only)* Confirm bot can post in reveal channel  
""")

@bot.command()
async def pvi(ctx, odds: str, purse: str, earnings: str):
    try:
        # Support both +11000 and 110/1 formats
        if '/' in odds:
            num, denom = map(float, odds.replace(' ', '').split('/'))
            odds_val = (num / denom) * 100
        else:
            odds_val = float(odds.replace('+', '').replace(',', '').strip())

        purse_val = float(purse.replace(',', '').strip())
        earnings_val = float(earnings.replace(',', '').strip())

        implied_prob = 100 / (odds_val + 100)
        relative_winnings = earnings_val / purse_val
        pvi_score = relative_winnings / implied_prob

        await ctx.send(f"""📈 **PVI Calculation**
• Odds: {'+' if '/' not in odds else ''}{odds}
• Implied Win Probability: {implied_prob*100:.4f}%
• Relative Winnings: {relative_winnings*100:.2f}%
• **PVI:** {pvi_score:.2f} {'✅' if pvi_score > 1 else '❌'}
""")
    except Exception as e:
        await ctx.send("❌ Error! Format: `!pvi 11000 9000000 1760000` or `!pvi 110/1 9000000 1760000`")

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

# === Allocation Command ===
@bot.command()
async def allocate(ctx, *, message):
    try:
        lines = message.strip().split('\n')
        first_line = lines[0].lower()
        if 'u' not in first_line or '$' not in first_line:
            await ctx.send("❌ Format should be like `!allocate 1u $10` followed by picks.")
            return

        # Parse allocation line
        unit_str, cash_str = first_line.split()
        total_units = float(unit_str.replace('u', ''))
        unit_value = float(cash_str.replace('$', ''))
        total_cash = total_units * unit_value

        # Parse picks
        picks = []
        for line in lines[1:]:
            if line.strip() == '': continue
            name, odds = line.rsplit(maxsplit=1)
            odds_num = float(odds.replace('/1',''))
            picks.append((name.strip(), odds_num))

        # Calculate target payout using harmonic mean method
        inverse_sum = sum(1 / odds for _, odds in picks)
        target_payout = total_cash / inverse_sum

        output = f"📊 **{total_units:.1f} Unit Allocation** (${total_cash:.2f} total):"
        for name, odds in picks:
            stake = target_payout / odds
            units = stake / unit_value
            payout = stake * odds
            output += f"\n• **{name}** — {units:.2f}u (${stake:.2f}) — win ${payout:.2f}"

        await ctx.send(output)

    except Exception as e:
        await ctx.send(f"❌ Error processing command: {str(e)}")

@bot.command()
async def mypick(ctx):
    user_id = str(ctx.author.id)
    picks_data = load_json(PICKS_FILE)  # Reload fresh data

    if user_id not in picks_data:
        await ctx.send("❌ You haven't submitted a pick yet. DM me your pick with `!pick Your Golfer`.")
        return

    user_pick = picks_data[user_id]
    name = user_pick["name"]
    pick = user_pick["pick"]
    timestamp = user_pick["timestamp"]

    await ctx.send(f"📌 **{name}**, your most recent pick was:\n**{pick}** *(submitted at {timestamp})*")

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
@bot.command()
async def submits(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ You're not authorized to use this command.")
        return

    if not picks:
        await ctx.send("📭 No picks have been submitted yet.")
        return

    msg = "**🕐 Pick Submission Times:**\n"
    for p in picks.values():
        name = p["name"]
        time = p["timestamp"]
        msg += f"- **{name}** submitted at `{time}`\n"

    await ctx.send(msg)

@tasks.loop(minutes=1)
async def dm_reminder_task():
    now = datetime.now(pytz.timezone('US/Eastern'))
    if now.strftime('%A') == 'Wednesday' and now.strftime('%H:%M') == '18:00':
        guild = discord.utils.get(bot.guilds)  # Gets the first server your bot is in
        if not guild:
            return

        for member in guild.members:
            if member.bot:
                continue
            try:
                await member.send("⏰ Heads up! Make sure to DM your pick by **9 PM tonight** using `!pick Your Golfer`.")
            except:
                pass  # Ignore users who have DMs turned off

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    auto_reveal_task.start()
    update_weeks_task.start()
    dm_reminder_task.start()  # 👈 Add this here too

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
