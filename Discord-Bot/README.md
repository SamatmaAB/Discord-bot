# CTFd Discord Monitor

A Discord bot that monitors a CTFd instance for new challenges and scoreboard changes.

## Features

-   **New Challenge Alerts**: Pings the configured channel when a new challenge is released.
-   **Scoreboard Updates**: Checks the scoreboard periodically (e.g., every 100s) and sends an update *only if* the scoreboard (score or rank) has changed.
-   **Slash Command**: `/status` - Instantly replies with the current scoreboard status and solve count.
-   **New Solve Alerts**: Alerts when your team solves a new challenge (configurable).

## Setup

1.  **Prerequisites**:
    -   Python 3.8+
    -   A Discord Bot Token (with `Message Content` intent enabled in the Developer Portal).

2.  **Installation**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configuration**:
    Create a `.env` file in the root directory:
    ```env
    DISCORD_TOKEN=your_discord_bot_token
    CTFD_TOKEN=your_ctfd_api_token
    CHANNEL_IDS=123456789012345678,987654321098765432
    CHECK_INTERVAL=100
    ```
    -   `CHECK_INTERVAL`: Time in seconds between checks.
    -   `CTFD_TOKEN`: Can be found in your CTFd profile settings.

4.  **Running**:
    ```bash
    python bot.py
    ```

## Commands

-   `/status`: Displays the current rank, score, and number of solved challenges for the tracked teams.
