# CTFd Discord Monitor

A comprehensive Discord bot that monitors a CTFd instance for new challenges, scoreboard changes, and remote scenario updates. Includes automatic temperature management for Raspberry Pi deployment.

## Features

-   **New Challenge Alerts**: Pings @everyone when a new challenge is released.
-   **Scoreboard Updates**: Checks the scoreboard periodically and sends an update with @everyone ping *only if* the scoreboard (score or rank) has changed.
-   **Remote Scenario Monitoring**: Detects when the remote scenario page updates and pings @everyone with the alert.
-   **New Solve Alerts**: Alerts @everyone when your team solves a new challenge.
-   **Slash Commands**:
    -   `/status` - Instantly replies with the current scoreboard status and solve count.
    -   `/temp` - Displays current Raspberry Pi CPU temperature with color-coded status.
-   **Temperature Management** (Pi-specific):
    -   Automatically monitors Pi CPU temperature
    -   Throttles bot at 85°C to reduce CPU usage
    -   Kills bot at 90°C or after 5 minutes of throttling
    -   Auto-restarts bot when temperature drops to 60°C
    -   Sends Discord alerts for all temperature events

## Setup

### Prerequisites

-   Python 3.8+
-   A Discord Bot Token (with `Message Content` intent enabled in the Developer Portal)
-   For Pi deployment: Raspberry Pi with `vcgencmd` available

### Installation

1. **Clone/Download the repository**
2. **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3. **Create a `.env` file** in the root directory:
    ```env
    DISCORD_TOKEN=your_discord_bot_token
    CTFD_TOKEN=your_ctfd_api_token
    CHANNEL_IDS=123456789012345678,987654321098765432
    CHECK_INTERVAL=100
    ```
    - `DISCORD_TOKEN`: Your Discord bot token
    - `CTFD_TOKEN`: Your CTFd API token (found in CTFd profile settings)
    - `CHANNEL_IDS`: Comma-separated Discord channel IDs (bot will send messages to all of them)
    - `CHECK_INTERVAL`: Seconds between CTFd checks (default: 100)

## Running

### Option 1: Local/Simple Deployment

Just run the bot:
```bash
python3 bot.py
```

### Option 2: Pi Deployment with Temperature Management (Recommended for Always-On)

This setup runs both the bot and temperature manager in `tmux` sessions for easy access and monitoring.

**Quick Start:**
```bash
# Make scripts executable
chmod +x startup.sh
chmod +x reboot-startup.sh

# Start both services
./startup.sh
```

**Attach to sessions:**
```bash
# Check running sessions
tmux list-sessions

# Attach to temperature manager
tmux attach-session -t temp_manager

# Attach to bot
tmux attach-session -t discord_bot

# Detach (Ctrl+B then D)
```

**Auto-Start on Pi Reboot:**

Follow the setup in `AUTOSTART_SETUP.md` to enable auto-start on reboot using crontab or systemd.

## File Structure

```
├── bot.py                      # Main Discord bot
├── temperature_manager.py      # Pi temperature monitoring and bot lifecycle management
├── startup.sh                  # Manual startup script (runs both in tmux)
├── reboot-startup.sh           # Auto-start script for crontab/systemd
├── requirements.txt            # Python dependencies
├── snapshot.json               # Bot state (auto-generated)
├── bot_state.json              # Temperature manager state (auto-generated)
├── README.md                   # This file
└── AUTOSTART_SETUP.md          # Auto-start configuration guide
```

## Commands

### `/status`
Displays the current rank, score, and number of solved challenges for tracked teams.

**Output:**
- Team rankings
- Score for each team
- Total challenges solved
- List of solved challenge names

### `/temp`
Displays the current Raspberry Pi CPU temperature.

**Output:**
- Current temperature in Celsius
- Color-coded status indicator:
  - 🟢 **Cool** (< 70°C)
  - 🟠 **Warm** (70-85°C)
  - 🔴 **Overheating** (≥ 85°C)

## Temperature Management Details

The `temperature_manager.py` script handles Pi thermal management:

| Temperature | Action |
|-------------|--------|
| < 60°C | Bot runs normally, no throttle |
| 60-85°C | Bot runs normally |
| 85°C+ | Throttles bot (reduces CPU priority) |
| 85°C+ for 5 min | Force kills bot |
| ≥ 90°C | Immediately kills bot |

**Discord Alerts Sent For:**
- ✅ Bot started
- ✅ Temperature exceeded threshold
- ✅ Bot throttled/killed
- ✅ Pi cooled down and bot resumed
- ✅ Temperature sensor errors
- ✅ Bot shutdown

## Configuration for Different CTFd Instances

Update these constants in `bot.py`:

```python
MY_TEAM = "Your Team Name"          # Your team name from scoreboard
RIVAL_TEAM = "Rival Team Name"      # Rival team to track
CTFD_BASE = "https://ectf.ctfd.io"  # CTFd instance URL
CHECK_INTERVAL = 100                # Seconds between checks (from .env)
```

## Troubleshooting

### Temperature readings fail on Pi
The script tries both `vcgencmd measure_temp` and `/sys/class/thermal/thermal_zone0/temp`. If both fail, you'll get an alert after 5 consecutive failures.

### Bot not receiving messages
- Verify `DISCORD_TOKEN` is correct
- Ensure bot has permissions in the target channels
- Check that `CHANNEL_IDS` are correct and bot is in those channels
- Verify `Message Content` intent is enabled in Discord Developer Portal

### tmux sessions not persisting
Make sure you're using `tmux attach-session` to view output, not spawning new terminals. The sessions persist in the background.

### Auto-start not working on Pi reboot
1. Verify crontab entry: `sudo crontab -e` and check the line exists
2. Check logs: `tail -f /var/log/discord-bot-startup.log` (if systemd version)
3. Ensure script paths are absolute, not relative

## Requirements

See `requirements.txt`:
```
discord.py>=2.0.0
aiohttp>=3.8.0
python-dotenv>=0.20.0
```

## Notes

- All alerts include @everyone mentions (except on bot startup)
- Snapshot state is saved after each check
- Temperature checks occur every 10 seconds (configurable in `temperature_manager.py`)
- The bot uses Discord embeds for formatted messages
- Compatible with Python 3.8+
