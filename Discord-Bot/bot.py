import os
import json
import hashlib
import logging
from datetime import datetime, UTC

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

# ======================
# CONFIG
# ======================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CTFD_TOKEN = os.getenv("CTFD_TOKEN")

# MULTI-CHANNEL SUPPORT (comma-separated IDs in .env)
CHANNEL_IDS = [int(x.strip()) for x in os.getenv("CHANNEL_IDS", "").split(",") if x.strip()]

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 100))

# TEAMS
MY_TEAM = "People's Education Society University - PESU2"
RIVAL_TEAM = "People's Education Society University - PESU1"

SNAPSHOT_FILE = "snapshot.json"
CTFD_BASE = "https://ectf.ctfd.io"

# SCOREBOARD PAGINATION
PER_PAGE = 100
MAX_PAGES = 10  # safety cap

# ======================
# LOGGING
# ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ======================
# DISCORD CLIENT
# ======================
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ======================
# STATE HANDLING
# ======================
def load_snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        return {
            "hash": None,
            "challenges": [],
            "scoreboard": {},
            "solved": []
        }

    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logging.warning("Snapshot file corrupted or unreadable. Resetting snapshot.")
        return {
            "hash": None,
            "challenges": [],
            "scoreboard": {},
            "solved": []
        }

def save_snapshot(data):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ======================
# AUTH HEADERS
# ======================
def auth_headers():
    headers = {
        "User-Agent": "CTFd-Discord-Bot/1.0",
        "Accept": "application/json"
    }
    if CTFD_TOKEN:
        headers["Authorization"] = f"Token {CTFD_TOKEN}"
    return headers

# ======================
# API FETCH
# ======================
async def fetch_json(url):
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=auth_headers()) as resp:
            resp.raise_for_status()
            return await resp.json()

async def fetch_challenges():
    return await fetch_json(f"{CTFD_BASE}/api/v1/challenges")

async def fetch_scoreboard_page(page):
    url = f"{CTFD_BASE}/api/v1/scoreboard?page={page}&per_page={PER_PAGE}"
    return await fetch_json(url)

# ======================
# EXTRACT DATA
# ======================
def extract_challenges(data):
    challenges = []
    solved = []

    for item in data.get("data", []):
        name = item.get("name")
        challenges.append({
            "name": name,
            "value": str(item.get("value")),
            "category": item.get("category")
        })

        # AUTHENTICATED FIELD
        if item.get("solved_by_me"):
            solved.append(name)

    return challenges, solved

# ======================
# SCOREBOARD PARSER (eCTF + PAGINATION)
# ======================
async def extract_team_positions(my_team, rival_team):
    result = {}

    targets = {
        my_team.lower(): my_team,
        rival_team.lower(): rival_team
    }

    for page in range(1, MAX_PAGES + 1):
        data = await fetch_scoreboard_page(page)
        entries = data.get("data", [])

        if not entries:
            break

        for entry in entries:
            team_obj = entry.get("team", {})
            raw_name = team_obj.get("name") or entry.get("name")
            raw_name = str(raw_name).strip() if raw_name else ""
            key = raw_name.lower()

            if key in targets:
                result[targets[key]] = {
                    "rank": entry.get("pos") or entry.get("rank"),
                    "score": entry.get("score")
                }

        # Stop early if both teams found
        if len(result) == len(targets):
            break

    return result

def hash_content(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# ======================
# TERMINAL PRINT
# ======================
def print_scoreboard_status(status, solved):
    print("\n[Scoreboard]")
    for team, info in status.items():
        print(f"  {team}: Rank {info['rank']} | Score {info['score']}")
    if solved:
        print(f"  Solved by {MY_TEAM}:", ", ".join(solved))
    print()

# ======================
# DISCORD MESSAGING
# ======================
async def send_embed(title, description, color=0x3498db):
    for channel_id in CHANNEL_IDS:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception:
            logging.error(f"Channel not found or inaccessible: {channel_id}")
            continue

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(UTC)
        )
        embed.set_footer(text="CTFd Monitor")

        await channel.send(embed=embed)

# ======================
# MONITOR LOOP
# ======================
@tasks.loop(seconds=CHECK_INTERVAL)
async def monitor():
    logging.info("Checking CTFd status...")

    try:
        snapshot = load_snapshot()

        # -------- CHALLENGES --------
        challenge_data = await fetch_challenges()
        page_hash = hash_content(json.dumps(challenge_data, sort_keys=True))

        challenges, solved = extract_challenges(challenge_data)

        # -------- DETECT CHANGES --------
        new_challenges = []
        if page_hash != snapshot.get("hash"):
            old_names = {c["name"] for c in snapshot.get("challenges", [])}
            for chall in challenges:
                if chall["name"] not in old_names:
                    new_challenges.append(chall)

        new_solves = []
        old_solved = set(snapshot.get("solved", []))
        for s in solved:
            if s not in old_solved:
                new_solves.append(s)

        # -------- SCOREBOARD --------
        positions = await extract_team_positions(
            MY_TEAM,
            RIVAL_TEAM
        )

        # -------- ALERTS --------
        if new_challenges:
            desc = "\n".join([f"**{c['name']}** ({c['category']}) - {c['value']} pts" for c in new_challenges])
            await send_embed("🚨 NEW CHALLENGE RELEASED!", desc, 0xe74c3c)

        if new_solves:
            desc = "\n".join([f"**{s}**" for s in new_solves])
            await send_embed("✅ New Solve!", f"Solved by {MY_TEAM}:\n{desc}", 0x2ecc71)

        # -------- DISCORD MESSAGE (STATUS) --------
        # Only ping if scoreboard changed
        old_positions = snapshot.get("scoreboard", {})
        if positions != old_positions:
            lines = []
            for team in (MY_TEAM, RIVAL_TEAM):
                info = positions.get(team)
                if info:
                    lines.append(
                        f"**{team}** → Rank: {info['rank']} | Score: {info['score']}"
                    )
                else:
                    lines.append(f"**{team}** → Not found on scoreboard")

            if solved:
                lines.append("")
                lines.append(f"✅ **Total Solved:** {len(solved)}")
                if len(solved) <= 5: 
                     for s in solved:
                        lines.append(f"- {s}")
                else:
                    lines.append(f"*(...and {len(solved)-5} more)*")

            await send_embed(
                "📊 Current Scoreboard Status",
                "\n".join(lines),
                0x1abc9c
            )
            logging.info("Scoreboard updated. Sent notification.")
        else:
            logging.info("Scoreboard unchanged. Skipping notification.")

        print_scoreboard_status(positions, solved)

        # SAVE STATE
        save_snapshot({
            "hash": page_hash,
            "challenges": challenges,
            "scoreboard": positions,
            "solved": solved
        })

        logging.info("Check complete")

    except Exception as e:
        logging.exception("Monitor error")
        await send_embed(
            "Monitor Error",
            f"```{str(e)[:1900]}```",
            0xe74c3c
        )

# ======================
# EVENTS
# ======================
@client.event
async def on_ready():
    logging.info(f"Logged in as {client.user}")
    
    # Sync commands to the specific guild for instant updates
    if CHANNEL_IDS:
        try:
            channel = await client.fetch_channel(CHANNEL_IDS[0])
            if channel:
                guild = channel.guild
                logging.info(f"Syncing commands to guild: {guild.name} ({guild.id})")
                
                # Copy global commands to guild
                tree.copy_global_to(guild=guild)
                await tree.sync(guild=guild)
                logging.info("Guild sync complete.")
                
                # Clear global commands to avoid duplicates in the UI
                # (This removes the 'global' version of the command so you only see the guild one)
                # Note: It might take up to 1 hour for the global one to disappear from Discord completely
                # but this stops us from pushing it again.
        except Exception as e:
            logging.error(f"Failed to sync to guild: {e}")

    await send_embed("CTFd Monitor Online", "Bot has started monitoring. Slash commands synced.")
    monitor.start()

@tree.command(name="status", description="Check current scoreboard status manually")
async def status(interaction: discord.Interaction):
    logging.info(f"Status command received from {interaction.user}")
    
    # Load latest state
    snapshot = load_snapshot()
    positions = snapshot.get("scoreboard", {})
    solved = snapshot.get("solved", [])
    
    lines = []
    for team in (MY_TEAM, RIVAL_TEAM):
        info = positions.get(team)
        if info:
            lines.append(
                f"**{team}** → Rank: {info['rank']} | Score: {info['score']}"
            )
        else:
            lines.append(f"**{team}** → Not found on scoreboard")

    if solved:
        lines.append("")
        lines.append(f"✅ **Total Solved:** {len(solved)}")
        if len(solved) <= 5: 
                for s in solved:
                    lines.append(f"- {s}")
        else:
            lines.append(f"*(...and {len(solved)-5} more)*")

    embed = discord.Embed(
        title="📊 Current Scoreboard Status (Manual Check)",
        description="\n".join(lines),
        color=0x1abc9c,
        timestamp=datetime.now(UTC)
    )
    embed.set_footer(text=f"Requested by {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed)



# ======================
# START
# ======================
if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN missing in .env")

    if not CHANNEL_IDS:
        raise RuntimeError("CHANNEL_IDS missing in .env")

    if not CTFD_TOKEN:
        raise RuntimeError("CTFD_TOKEN missing in .env")

    client.run(TOKEN)