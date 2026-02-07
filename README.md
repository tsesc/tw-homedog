# tw-homedog

Taiwan Real Estate Smart Listing Notifier — 自動監控 591 新房源並透過 Telegram 即時通知。

支援**買房** (`sale.591.com.tw`) 和**租屋** (`rent.591.com.tw`) 兩種模式。

## Quick Start (Docker)

```bash
# 1. Copy environment file
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID

# 2. Start
docker compose up -d

# 3. Open Telegram, send /start to your bot
```

## Quick Start (Local)

```bash
# Install dependencies
uv sync

# Install Playwright browsers
uv run playwright install chromium

# Start Bot mode
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy uv run python -m tw_homedog
```

## Bot Commands

在 Telegram 中與 Bot 互動：

| 指令 | 說明 |
|------|------|
| `/start` | 首次設定引導 / 歡迎訊息 |
| `/settings` | 修改搜尋條件（模式、區域、價格、坪數、關鍵字、排程） |
| `/status` | 查看當前設定、排程狀態、物件統計 |
| `/run` | 手動觸發爬取 + 通知 |
| `/pause` | 暫停自動排程 |
| `/resume` | 恢復自動排程 |
| `/loglevel` | 調整日誌等級（DEBUG/INFO/WARNING/ERROR） |

## Environment Variables

| 變數 | 必要 | 預設 | 說明 |
|------|------|------|------|
| `TELEGRAM_BOT_TOKEN` | Yes | - | @BotFather 取得的 Bot Token |
| `TELEGRAM_CHAT_ID` | Yes | - | 授權的 Chat ID |
| `DATABASE_PATH` | No | `data/homedog.db` | SQLite 資料庫路徑 |
| `LOG_LEVEL` | No | `INFO` | 日誌等級 |

## CLI Mode (Legacy)

仍可使用傳統 YAML 配置 + 一次性執行模式：

```bash
# Copy config
cp config.example.yaml config.yaml
# Edit config.yaml

# Run pipeline
uv run python -m tw_homedog cli run
uv run python -m tw_homedog cli scrape
uv run python -m tw_homedog cli notify
```

## Configuration

### Bot Mode

所有設定透過 Telegram Bot inline keyboard 管理，儲存在 SQLite `bot_config` 表中。

首次啟動時傳送 `/start` 開始設定引導，之後隨時可用 `/settings` 修改任何參數。

### CLI Mode

`config.yaml` 設定說明：

```yaml
search:
  mode: buy              # "buy" or "rent"
  region: "台北市"        # 中文名稱或數字代碼 (1)，支援全台 22 縣市
  districts:
    - 南港區
    - 內湖區
  price:
    min: 2000            # buy: 萬, rent: NTD/月
    max: 3000
  size:
    min_ping: 20         # optional
  keywords:
    include: []          # all must match
    exclude: []          # any excludes
  max_pages: 3

telegram:
  bot_token: "YOUR_BOT_TOKEN_HERE"
  chat_id: "YOUR_CHAT_ID_HERE"
```

更多使用情境的設定範例請參考 `config.examples/` 目錄。

## Docker

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

Data is persisted in Docker volumes (`homedog-data`, `homedog-logs`).

## Telegram Bot Setup

1. 在 Telegram 找 @BotFather
2. 用 `/newbot` 建立新 bot
3. 記下 bot token
4. 向你的 bot 發送訊息，然後從 `https://api.telegram.org/bot<TOKEN>/getUpdates` 取得 chat ID
5. 設定環境變數或填入 `.env`

## Tests

```bash
uv run pytest -v
```
