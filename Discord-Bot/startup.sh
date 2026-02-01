#!/bin/bash

# Startup script for Discord Bot on Raspberry Pi
# This script starts both the temperature manager and bot in tmux sessions
# Run this on Pi startup or manually

cd /home/pi/Discord-Bot  # Change this to your actual path

# Kill existing sessions if they exist
tmux kill-session -t temp_manager 2>/dev/null
tmux kill-session -t discord_bot 2>/dev/null

# Create new tmux sessions
tmux new-session -d -s temp_manager -x 200 -y 50
tmux send-keys -t temp_manager "python3 temperature_manager.py" Enter

sleep 2  # Wait for temp manager to start

tmux new-session -d -s discord_bot -x 200 -y 50
tmux send-keys -t discord_bot "python3 bot.py" Enter

echo "✅ Both sessions started!"
echo "Attach to temp_manager: tmux attach-session -t temp_manager"
echo "Attach to discord_bot: tmux attach-session -t discord_bot"
