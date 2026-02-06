# tw-homedog

Taiwan Real Estate Smart Listing Notifier — 自動監控 591 新房源並透過 Telegram 即時通知。

## Setup

```bash
# Install dependencies
uv sync

# Install Playwright browsers
uv run playwright install chromium

# Configure
cp config.example.yaml config.yaml
# Edit config.yaml with your search criteria and Telegram bot token
```

## Usage

```bash
# Full pipeline: scrape → match → notify
uv run python -m tw_homedog run

# Scrape and store only (no notifications)
uv run python -m tw_homedog scrape

# Match and notify only (from existing DB)
uv run python -m tw_homedog notify

# Use custom config path
uv run python -m tw_homedog run --config /path/to/config.yaml
```

## Cron Setup

Run every 15 minutes:

```bash
crontab -e
```

Add:

```
*/15 * * * * cd /path/to/tw-homedog && /path/to/.local/bin/uv run python -m tw_homedog run >> /var/log/tw-homedog.log 2>&1
```

## Telegram Bot Setup

1. Message @BotFather on Telegram
2. Create a new bot with `/newbot`
3. Copy the bot token to `config.yaml`
4. Message your bot, then get your chat ID from `https://api.telegram.org/bot<TOKEN>/getUpdates`

## Tests

```bash
uv run pytest -v
```
