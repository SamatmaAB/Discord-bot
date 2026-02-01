# Auto-Start Setup Instructions

Follow these steps on your Raspberry Pi to make the bot auto-start on reboot:

## Step 1: Make scripts executable
```bash
chmod +x /home/pi/Discord-Bot/startup.sh
chmod +x /home/pi/Discord-Bot/reboot-startup.sh
```

## Step 2: Set up auto-start with crontab

Run this command on the Pi:
```bash
sudo crontab -e
```

Then add this line at the bottom:
```
@reboot /home/pi/Discord-Bot/reboot-startup.sh
```

(Replace `/home/pi/Discord-Bot` with your actual path if different)

## Step 3: Allow tmux to work in cron

The reboot script needs to display tmux sessions. Add this to the crontab as well:
```
@reboot sleep 5 && export DISPLAY=:0 && /home/pi/Discord-Bot/reboot-startup.sh
```

## Step 4: Create log directory (optional but recommended)
```bash
sudo touch /var/log/discord-bot-startup.log
sudo chmod 666 /var/log/discord-bot-startup.log
```

## Step 5: Test it
Reboot your Pi:
```bash
sudo reboot
```

Then SSH back in and check:
```bash
tmux list-sessions
```

You should see both `temp_manager` and `discord_bot` sessions running!

## Verify it worked
```bash
# Check if sessions are running
tmux list-sessions

# Attach to check logs
tmux attach-session -t temp_manager
```

---

### Alternative: Using systemd (More reliable for always-on)

If you prefer systemd instead of cron, create `/etc/systemd/system/discord-bot-startup.service`:

```ini
[Unit]
Description=Discord Bot Auto-Startup
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=pi
ExecStart=/home/pi/Discord-Bot/reboot-startup.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Then enable it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable discord-bot-startup.service
sudo systemctl start discord-bot-startup.service
```

Check status:
```bash
sudo systemctl status discord-bot-startup.service
```
