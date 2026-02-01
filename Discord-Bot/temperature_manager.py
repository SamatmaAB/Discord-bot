import os
import subprocess
import time
import logging
import json
import asyncio
import aiohttp
from datetime import datetime, UTC
from dotenv import load_dotenv
import signal

# ======================
# PATHS (CRITICAL)
# ======================
PROJECT_DIR = "/home/pesu2/Discord-bot/Discord-Bot"
VENV_PY = f"{PROJECT_DIR}/venv/bin/python"
BOT_SCRIPT = f"{PROJECT_DIR}/bot.py"
STATE_FILE = f"{PROJECT_DIR}/bot_state.json"

# ======================
# CONFIG
# ======================
load_dotenv(os.path.join(PROJECT_DIR, ".env"))

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_IDS = [int(x.strip()) for x in os.getenv("CHANNEL_IDS", "").split(",") if x.strip()]

# Temperature thresholds
TEMP_ALERT_THRESHOLD = 85
TEMP_RESUME_THRESHOLD = 60
TEMP_KILL_THRESHOLD = 90
THROTTLE_DURATION = 300
CHECK_INTERVAL = 10
DISCORD_RETRY_DELAY = 30

# Process management
BOT_PROCESS = None
BOT_PID = None
IS_THROTTLED = False
THROTTLE_START_TIME = None
MAX_RESTART_ATTEMPTS = 3
RESTART_ATTEMPTS = 0

# ======================
# LOGGING
# ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ======================
# STATE MANAGEMENT
# ======================
def save_state(data):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save state: {e}")

# ======================
# TEMPERATURE CHECK
# ======================
def get_pi_temperature():
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return float(result.stdout.split("=")[1].replace("'C", ""))
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read()) / 1000
    except Exception as e:
        logging.error(f"Temperature read failed: {e}")
        return None

# ======================
# BOT PROCESS CONTROL
# ======================
def start_bot():
    global BOT_PROCESS, BOT_PID, IS_THROTTLED, RESTART_ATTEMPTS

    if BOT_PROCESS and BOT_PROCESS.poll() is None:
        return True

    try:
        logging.info("Starting bot via venv python...")
        BOT_PROCESS = subprocess.Popen(
            [VENV_PY, BOT_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid  # ensures clean kill tree
        )
        BOT_PID = BOT_PROCESS.pid
        IS_THROTTLED = False
        RESTART_ATTEMPTS = 0
        save_state({"bot_running": True, "throttled": False})
        logging.info(f"Bot started (PID {BOT_PID})")
        return True
    except Exception as e:
        logging.error(f"Bot start failed: {e}")
        RESTART_ATTEMPTS += 1
        return False

def stop_bot(force=False):
    global BOT_PROCESS, BOT_PID, IS_THROTTLED

    if not BOT_PROCESS or BOT_PROCESS.poll() is not None:
        return True

    try:
        logging.warning(f"Stopping bot (PID {BOT_PID})")
        os.killpg(os.getpgid(BOT_PID), signal.SIGTERM)
        BOT_PROCESS.wait(timeout=10)
    except Exception:
        os.killpg(os.getpgid(BOT_PID), signal.SIGKILL)

    BOT_PROCESS = None
    BOT_PID = None
    IS_THROTTLED = False
    save_state({"bot_running": False, "throttled": False})
    return True

def throttle_bot():
    global IS_THROTTLED, THROTTLE_START_TIME
    if BOT_PID and not IS_THROTTLED:
        subprocess.run(["renice", "+10", str(BOT_PID)], check=False)
        IS_THROTTLED = True
        THROTTLE_START_TIME = time.time()

def unthrottle_bot():
    global IS_THROTTLED
    if BOT_PID and IS_THROTTLED:
        subprocess.run(["renice", "0", str(BOT_PID)], check=False)
        IS_THROTTLED = False

# ======================
# DISCORD ALERTS
# ======================
async def send_alert(title, description, color):
    for channel_id in CHANNEL_IDS:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {TOKEN}"},
                json={"embeds": [{
                    "title": title,
                    "description": description,
                    "color": color,
                    "timestamp": datetime.now(UTC).isoformat()
                }]}
            )

# ======================
# MAIN LOOP
# ======================
async def monitor_temperature():
    logging.info("Temperature monitor online")
    await send_alert("🌡️ Monitor Online", "Temperature manager started.", 0x2ecc71)

    start_bot()

    while True:
        temp = get_pi_temperature()
        if temp is None:
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        logging.info(f"Temperature: {temp}°C")

        if temp >= TEMP_ALERT_THRESHOLD:
            throttle_bot()
            if temp >= TEMP_KILL_THRESHOLD:
                await send_alert("🔥 BOT KILLED", f"Temp {temp}°C", 0xe74c3c)
                stop_bot(force=True)

        elif temp < TEMP_RESUME_THRESHOLD:
            if BOT_PROCESS is None or BOT_PROCESS.poll() is not None:
                await send_alert("❄️ Restarting Bot", f"Temp {temp}°C", 0x2ecc71)
                start_bot()
            elif IS_THROTTLED:
                unthrottle_bot()

        await asyncio.sleep(CHECK_INTERVAL)

# ======================
# ENTRY
# ======================
if __name__ == "__main__":
    if not TOKEN or not CHANNEL_IDS:
        raise RuntimeError("Missing DISCORD_TOKEN or CHANNEL_IDS")

    asyncio.run(monitor_temperature())
