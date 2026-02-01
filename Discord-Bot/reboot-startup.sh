#!/bin/bash

# Cron job for Pi reboot - starts Discord bot and temperature manager
# This script should be placed in /etc/cron.d/ or added to root's crontab

cd /home/pesu2/Discord-bot/Discord-bot

# Kill any existing sessions to avoid duplicates
tmux kill-session -t temp_manager 2>/dev/null
tmux kill-session -t discord_bot 2>/dev/null

sleep 1

# Create new tmux sessions
tmux new-session -d -s temp_manager -x 200 -y 50
tmux send-keys -t temp_manager "python3 temperature_manager.py" Enter

sleep 2

tmux new-session -d -s discord_bot -x 200 -y 50
tmux send-keys -t discord_bot "python3 bot.py" Enter

# Log the startup
echo "$(date): Bot and Temperature Manager started on Pi reboot" >> /var/log/discord-bot-startup.log
