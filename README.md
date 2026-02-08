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

## Telegram 縮圖（Google Maps）

個人用量通常 <10k 次/月，Google Maps Static Maps + Geocoding 都有每月 10,000 次免費額度，超出後才計費。  
需求：Google Cloud 專案 + 啟用 Static Maps API 與 Geocoding API + API key。

### 如何在 Google Cloud Console 取得並限制 API Key（從零開始）
1. 進入 [console.cloud.google.com](https://console.cloud.google.com/)，建立新專案（例如 `homedog-maps`），若要求請綁定結算帳戶。
2. 左側「API 和服務」→「程式庫」→ 啟用 **Maps Static API** 與 **Geocoding API**。
3. 「API 和服務」→「認證」→「建立認證」→ **API 金鑰**，建立後點「限制金鑰」：
   - 應用限制：選「IP 位址」，填你的伺服器/本機出口 IP（不填也可，但風險較高）。
   - API 限制：選「限制鍵」，勾 **Maps Static API** 與 **Geocoding API**。
4. 設每日配額防爆：在兩個 API 的「配額」頁面，將「Requests per day」改成例如 9000（低於免費 10k）。
5. 複製產生的 API Key，供下方設定使用。

### Bot 模式（DB 設定）
1. 在 Google Cloud Console 建立或選擇專案，啟用 **Static Maps API** 與 **Geocoding API**，建立 API Key，建議設定 **每日配額** 以防暴衝（例如 9,000/天）。  
2. 將 Maps 設定寫入 SQLite `bot_config`（預設路徑 `data/homedog.db`，若環境變數 `DATABASE_PATH` 不同請替換）：  
   ```bash
   python - <<'PY'
   import sqlite3, json, os
   db = os.environ.get("DATABASE_PATH", "data/homedog.db")
   conn = sqlite3.connect(db)
   def set_k(k,v):
       conn.execute(
           "INSERT INTO bot_config (key,value,updated_at) VALUES (?,?,datetime('now')) "
           "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
           (k, json.dumps(v, ensure_ascii=False))
       )
   for k,v in {
       "maps.enabled": True,
       "maps.api_key": "YOUR_GOOGLE_MAPS_API_KEY",
       "maps.base_url": "https://maps.googleapis.com/maps/api/staticmap",
       "maps.size": "640x400",
       "maps.zoom": 16,
       "maps.scale": 2,
       "maps.language": "zh-TW",
       "maps.region": "tw",
       "maps.timeout": 6,
       "maps.cache_ttl_seconds": 86400,
       "maps.cache_dir": "data/map_cache",
       "maps.style": None,
   }.items():
       set_k(k, v)
   conn.commit(); conn.close()
   print("Maps config updated in", db)
   PY
   ```
3. 重啟 bot（或重新部署容器）。新的通知會嘗試產出地圖縮圖，失敗時自動降級為純文字地址。

### CLI / config.yaml
若仍使用 YAML：在 `config.yaml` 增加下列區塊即可（與 `telegram` 平行）：
```yaml
maps:
  enabled: true
  api_key: YOUR_GOOGLE_MAPS_API_KEY
  base_url: "https://maps.googleapis.com/maps/api/staticmap"
  size: "640x400"
  zoom: 16
  scale: 2
  language: "zh-TW"
  region: "tw"
  timeout: 6
  cache_ttl_seconds: 86400
  cache_dir: "data/map_cache"
  style: null
```

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
  room_counts: []        # e.g. [2,3] 房數，留空表示不限
  bathroom_counts: []    # e.g. [1,2] 衛浴數，留空表示不限
  size:
    min_ping: 20         # optional
    max_ping: null       # optional
  year_built:
    min: null            # optional, 建造年份
    max: null
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
