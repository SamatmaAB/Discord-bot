import os
import subprocess
import time
import logging
import json
import asyncio
import aiohttp
from datetime import datetime, UTC
from dotenv import load_dotenv

# ======================
# CONFIG
# ======================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_IDS = [int(x.strip()) for x in os.getenv("CHANNEL_IDS", "").split(",") if x.strip()]

# Temperature thresholds
TEMP_ALERT_THRESHOLD = 85  # Start monitoring/throttling
TEMP_RESUME_THRESHOLD = 60  # Resume bot
TEMP_KILL_THRESHOLD = 90  # Force kill if too hot
THROTTLE_DURATION = 300  # seconds to throttle before killing
CHECK_INTERVAL = 10  # seconds between temperature checks
DISCORD_RETRY_DELAY = 30  # seconds between Discord alert retries

# Process management
BOT_SCRIPT = "bot.py"
BOT_PROCESS = None
BOT_PID = None
IS_THROTTLED = False
THROTTLE_START_TIME = None
STATE_FILE = "bot_state.json"
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
    """Save the current state to a file."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save state: {e}")

def load_state():
    """Load the current state from a file."""
    if not os.path.exists(STATE_FILE):
        return {"bot_running": False, "throttled": False}
    
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load state: {e}")
        return {"bot_running": False, "throttled": False}

# ======================
# TEMPERATURE CHECK
# ======================
def get_pi_temperature():
    """
    Get the Raspberry Pi CPU temperature.
    Returns float temperature in Celsius, or None if failed.
    """
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Output format: "temp=54.0'C"
            temp_str = result.stdout.strip().split("=")[1].replace("'C", "")
            return float(temp_str)
        else:
            logging.warning("vcgencmd failed, trying alternative method...")
            # Fallback: read from thermal zone
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_millic = int(f.read().strip())
                return temp_millic / 1000.0
    except Exception as e:
        logging.error(f"Failed to get temperature: {e}")
        return None

# ======================
# PROCESS MANAGEMENT
# ======================
def start_bot():
    """Start the Discord bot process."""
    global BOT_PROCESS, BOT_PID, IS_THROTTLED, RESTART_ATTEMPTS
    
    if BOT_PROCESS and BOT_PROCESS.poll() is None:
        logging.info("Bot is already running.")
        RESTART_ATTEMPTS = 0
        return True
    
    try:
        logging.info("Starting bot process...")
        BOT_PROCESS = subprocess.Popen(
            ["python3", BOT_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        BOT_PID = BOT_PROCESS.pid
        IS_THROTTLED = False
        RESTART_ATTEMPTS = 0
        save_state({"bot_running": True, "throttled": False})
        logging.info(f"Bot started with PID {BOT_PID}")
        return True
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        RESTART_ATTEMPTS += 1
        if RESTART_ATTEMPTS >= MAX_RESTART_ATTEMPTS:
            logging.critical(f"Failed to start bot after {MAX_RESTART_ATTEMPTS} attempts!")
            RESTART_ATTEMPTS = 0
        return False

def throttle_bot():
    """
    Reduce CPU usage by increasing the nice value (lower priority).
    This is less disruptive than killing the process.
    """
    global IS_THROTTLED, THROTTLE_START_TIME
    
    if not BOT_PID or IS_THROTTLED:
        return
    
    try:
        logging.info(f"Throttling bot (PID {BOT_PID}) to reduce CPU usage...")
        # Increase nice value to reduce priority (lower priority = less CPU time)
        subprocess.run(["renice", "+10", str(BOT_PID)], check=True)
        IS_THROTTLED = True
        THROTTLE_START_TIME = time.time()
        save_state({"bot_running": True, "throttled": True})
        logging.info("Bot throttled successfully")
    except Exception as e:
        logging.error(f"Failed to throttle bot: {e}")

def unthrottle_bot():
    """Restore bot to normal priority."""
    global IS_THROTTLED
    
    if not BOT_PID or not IS_THROTTLED:
        return
    
    try:
        logging.info(f"Unthrottling bot (PID {BOT_PID})...")
        # Reset nice value to 0 (normal priority)
        subprocess.run(["renice", "0", str(BOT_PID)], check=True)
        IS_THROTTLED = False
        save_state({"bot_running": True, "throttled": False})
        logging.info("Bot unthrottled successfully")
    except Exception as e:
        logging.error(f"Failed to unthrottle bot: {e}")

def stop_bot(force=False):
    """Stop the Discord bot process."""
    global BOT_PROCESS, BOT_PID, IS_THROTTLED
    
    if not BOT_PROCESS or BOT_PROCESS.poll() is not None:
        logging.info("Bot is not running.")
        return True
    
    try:
        if force:
            logging.warning(f"Force killing bot (PID {BOT_PID})...")
            BOT_PROCESS.kill()
        else:
            logging.info(f"Gracefully stopping bot (PID {BOT_PID})...")
            BOT_PROCESS.terminate()
            # Wait up to 10 seconds for graceful shutdown
            try:
                BOT_PROCESS.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logging.warning("Bot didn't stop gracefully, force killing...")
                BOT_PROCESS.kill()
        
        BOT_PID = None
        IS_THROTTLED = False
        save_state({"bot_running": False, "throttled": False})
        logging.info("Bot stopped")
        return True
    except Exception as e:
        logging.error(f"Failed to stop bot: {e}")
        return False

# ======================
# DISCORD ALERTS
# ======================
async def send_alert(title, description, color=0x3498db):
    """Send an alert embed to Discord channels with retry logic."""
    for channel_id in CHANNEL_IDS:
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                    headers = {"Authorization": f"Bot {TOKEN}"}
                    
                    embed = {
                        "title": title,
                        "description": description,
                        "color": color,
                        "timestamp": datetime.now(UTC).isoformat()
                    }
                    
                    payload = {"embeds": [embed]}
                    
                    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 204 or resp.status == 200:
                            logging.info(f"Alert sent to channel {channel_id}")
                            break
                        else:
                            logging.warning(f"Failed to send alert (status {resp.status}), retrying...")
                            retry_count += 1
            except asyncio.TimeoutError:
                logging.warning(f"Discord alert timeout, retrying... ({retry_count + 1}/{max_retries})")
                retry_count += 1
            except Exception as e:
                logging.warning(f"Failed to send Discord alert: {e}, retrying... ({retry_count + 1}/{max_retries})")
                retry_count += 1
            
            if retry_count < max_retries:
                await asyncio.sleep(DISCORD_RETRY_DELAY)

# ======================
# MAIN MONITORING LOOP
# ======================
async def monitor_temperature():
    """Main temperature monitoring loop."""
    global BOT_PROCESS, BOT_PID, IS_THROTTLED, THROTTLE_START_TIME
    
    logging.info("Temperature monitor starting...")
    await send_alert(
        "🌡️ Temperature Monitor Online",
        "The Pi temperature monitor is now running. Bot will be managed automatically.",
        0x2ecc71
    )
    
    # Start bot initially
    start_bot()
    
    overheating_alerted = False
    cooling_alerted = False
    consecutive_errors = 0
    
    while True:
        try:
            temp = get_pi_temperature()
            
            if temp is None:
                consecutive_errors += 1
                logging.warning(f"Could not read temperature ({consecutive_errors} consecutive errors)")
                if consecutive_errors >= 5:
                    logging.error("Too many consecutive temperature read errors!")
                    await send_alert(
                        "⚠️ Temperature Sensor Error",
                        "Could not read Pi temperature for 5 consecutive checks. Please investigate.",
                        0xe74c3c
                    )
                    consecutive_errors = 0
                await asyncio.sleep(CHECK_INTERVAL)
                continue
            
            consecutive_errors = 0
            logging.info(f"Current temperature: {temp}°C")
            
            # ========== TEMPERATURE TOO HIGH ==========
            if temp >= TEMP_ALERT_THRESHOLD:
                if not overheating_alerted:
                    await send_alert(
                        "🔥 Pi is Overheating!",
                        f"Temperature reached {temp}°C. Throttling bot to cool down...",
                        0xe74c3c
                    )
                    overheating_alerted = True
                    cooling_alerted = False
                
                # Check if bot is running
                if BOT_PROCESS and BOT_PROCESS.poll() is None:
                    # Try throttling first
                    if not IS_THROTTLED:
                        throttle_bot()
                    
                    # If still too hot after throttle duration, kill it
                    if IS_THROTTLED and THROTTLE_START_TIME:
                        time_throttled = time.time() - THROTTLE_START_TIME
                        if time_throttled > THROTTLE_DURATION or temp >= TEMP_KILL_THRESHOLD:
                            logging.warning(f"Killing bot after {time_throttled}s throttle (temp: {temp}°C)")
                            await send_alert(
                                "💀 Bot Killed - Overheating",
                                f"Bot was killed after {int(time_throttled)}s of throttling. Temperature: {temp}°C",
                                0xe74c3c
                            )
                            stop_bot(force=True)
            
            # ========== TEMPERATURE COOLING DOWN ==========
            elif temp < TEMP_RESUME_THRESHOLD:
                # If bot was stopped or throttled, restart it
                if not BOT_PROCESS or BOT_PROCESS.poll() is not None:
                    if not cooling_alerted:
                        await send_alert(
                            "❄️ Pi Cooled Down",
                            f"Temperature is now {temp}°C. Restarting bot...",
                            0x2ecc71
                        )
                        cooling_alerted = True
                        overheating_alerted = False
                    
                    start_bot()
                elif IS_THROTTLED:
                    await send_alert(
                        "❄️ Pi Cooled Down",
                        f"Temperature is now {temp}°C. Removing throttle...",
                        0x2ecc71
                    )
                    unthrottle_bot()
                    cooling_alerted = True
                    overheating_alerted = False
            
            # ========== MODERATE TEMPERATURE ==========
            else:
                # Between thresholds - if throttled, keep monitoring
                if IS_THROTTLED:
                    logging.info(f"Temperature cooling down ({temp}°C). Still throttled.")
            
            await asyncio.sleep(CHECK_INTERVAL)
        
        except KeyboardInterrupt:
            logging.info("Shutting down temperature monitor...")
            await send_alert(
                "🛑 Temperature Monitor Stopped",
                "The temperature monitor has been stopped. Bot will no longer be managed.",
                0xf39c12
            )
            stop_bot()
            break
        except Exception as e:
            logging.exception(f"Error in monitoring loop: {e}")
            consecutive_errors += 1
            await asyncio.sleep(CHECK_INTERVAL)

# ======================
# START
# ======================
if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN missing in .env")
    
    if not CHANNEL_IDS:
        raise RuntimeError("CHANNEL_IDS missing in .env")
    
    asyncio.run(monitor_temperature())
