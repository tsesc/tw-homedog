# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                                # Install dependencies
uv run playwright install chromium     # Install browser (required for scraper)
uv run pytest -v                       # Run all tests
uv run pytest tests/test_scraper.py    # Run single test file
uv run pytest -k "test_price"          # Run tests matching pattern

# Bot mode (default) — long-running Telegram Bot with interactive config
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy uv run python -m tw_homedog

# CLI mode — one-shot pipeline execution (legacy)
uv run python -m tw_homedog cli run        # Full pipeline: scrape → match → notify
uv run python -m tw_homedog cli scrape     # Scrape + store only
uv run python -m tw_homedog cli notify     # Match + notify from existing DB

# Docker
docker compose up -d                   # Start Bot mode with Docker
docker compose logs -f                 # View logs
```

## Architecture

Two modes of operation:
- **Bot mode** (default): Long-running Telegram Bot with inline keyboard config, built-in scheduler
- **CLI mode** (`cli` subcommand): One-shot pipeline execution for YAML-based config

Pipeline: `scraper → normalizer → storage → matcher → notifier`

- **bot.py** — Telegram Bot Application with ConversationHandler for setup, InlineKeyboard for settings, JobQueue for scheduling
- **db_config.py** — SQLite-based config storage (key-value), replaces YAML in Bot mode. Supports `build_config()` to create Config dataclass from DB
- **log.py** — Structured logging with RotatingFileHandler, configurable via `LOG_LEVEL` env var
- **regions.py** — Comprehensive region/district code data for all 22 Taiwan counties/cities. Buy section codes for all regions; rent section codes for Taipei only. Provides `resolve_region()` and `resolve_districts()` helpers, plus `EN_TO_ZH` mapping for backward compatibility with English district names.
- **scraper.py** — Two modes with different strategies:
  - **Buy mode**: Playwright bootstraps session (CSRF token + cookies) → `requests` calls BFF API (`bff-house.591.com.tw/v1/web/sale/list`)
  - **Rent mode**: Playwright collects listing IDs from search pages → `requests` fetches detail HTML. Only Taipei is verified.
  - Buy/rent have completely different district codes (e.g., 內湖區: buy=10, rent=5)
- **normalizer.py** — Converts raw scraped dicts to unified format with SHA256 content hash
- **storage.py** — SQLite with WAL mode. Tables: `listings`, `notifications_sent`, `bot_config`
- **matcher.py** — Filters unnotified listings by price/district/size/keywords
- **notifier.py** — Telegram Bot API with asyncio. Max 10 per batch, 1s between messages
- **config.py** — YAML loader with dotted-key validation, dataclass-based config objects (CLI mode). Resolves Chinese region names ("台北市"→1) and converts English district names to Chinese ("Neihu"→"內湖區") for backward compatibility.

## Bot Commands

- `/start` — First-time guided setup or welcome message
- `/settings` — Modify any parameter via inline keyboard (mode, districts, price, size, keywords, schedule)
- `/status` — Current config summary, schedule status, DB stats
- `/run` — Manual pipeline trigger
- `/pause` / `/resume` — Control automatic scheduling
- `/loglevel DEBUG|INFO|WARNING|ERROR` — Dynamic log level adjustment

## Key Technical Gotchas

- 591 API `total` field is a **string**, must cast to `int`
- 591 API `totalPrice` parameter is **ignored** — price filtering must be client-side in matcher
- Playwright `document.cookie` is blocked on 591 — use `page.context.cookies()` instead
- Buy mode price unit is 萬 (10k NTD), rent mode is NTD — config `price.min/max` must match the mode
- `notifier.py` uses `asyncio.run()` inside sync code for Telegram async API
- `python-telegram-bot[job-queue]` extra is required for JobQueue/APScheduler support

## Environment Variables (Bot mode)

- `TELEGRAM_BOT_TOKEN` (required) — Bot token from @BotFather
- `TELEGRAM_CHAT_ID` (required) — Authorized chat ID
- `DATABASE_PATH` (default: `data/homedog.db`) — SQLite DB path
- `LOG_LEVEL` (default: `INFO`) — Logging level

## Config

**Bot mode**: Config stored in SQLite `bot_config` table, managed via Telegram inline keyboard.
**CLI mode**: YAML config at `config.yaml` (copy from `config.example.yaml`). See `config.examples/` for use-case-specific samples.

Config supports Chinese-first format: `region: "台北市"`, `districts: ["內湖區", "南港區"]`. English names (`region: 1`, `districts: ["Neihu"]`) still work for backward compatibility. All 22 Taiwan counties/cities are supported for buy mode; rent mode only supports Taipei.

## Testing

Tests use `tmp_path` for isolated SQLite DBs. External APIs (Telegram, 591) are mocked. Test helpers like `_listing(**overrides)` create test data with sensible defaults.
