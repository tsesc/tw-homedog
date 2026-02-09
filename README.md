# tw-homedog

Taiwan Real Estate Smart Listing Notifier — 自動監控 591 新房源並透過 Telegram Bot 互動式瀏覽。

支援**買房** (`sale.591.com.tw`) 和**租屋** (`rent.591.com.tw`) 兩種模式。

## Features

- **自動爬取** — 定時從 591 抓取新物件，支援多地區同時搜尋（如台北市+新北市）
- **智慧篩選** — 依價格、區域、坪數、關鍵字（包含/排除）自動過濾
- **互動式瀏覽** — `/list` 指令提供分頁瀏覽、區域篩選、詳情展開、一鍵標記已讀
- **已讀追蹤** — 以內容 hash 追蹤已讀狀態，物件更新時自動重新顯示
- **收藏功能** — 星號收藏感興趣的物件，`/favorites` 隨時查看
- **跨仲介去重** — `entity_fingerprint` + 相似度評分，自動合併同一房屋的不同刊登
- **物件詳情** — 買房模式自動 enrich 社區名、車位、公設比、格局等關鍵資訊
- **地圖縮圖** — 可選 Google Maps Static API，在通知中附上位置預覽
- **全 Telegram 操作** — 所有設定透過 inline keyboard 完成，無需編輯設定檔
- **Docker 一鍵部署** — `docker compose up -d` 即可運行

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
| `/list` | 互動式瀏覽未讀物件（最新優先、分頁、篩選、詳情、標記已讀） |
| `/favorites` | 查看收藏的物件 |
| `/settings` | 修改搜尋條件（模式、地區、區域、價格、坪數、關鍵字、排程） |
| `/status` | 查看當前設定、排程狀態、物件統計 |
| `/help` | 指令列表 |
| `/run` | 手動觸發爬取 |
| `/dedupall [batch_size]` | 以 batch 方式執行全庫去重 |
| `/pause` / `/resume` | 暫停 / 恢復自動排程 |
| `/loglevel` | 調整日誌等級（DEBUG/INFO/WARNING/ERROR） |
| `/config_export` | 匯出目前設定為 JSON |
| `/config_import` | 匯入設定（JSON） |

## How It Works

```
排程觸發 → 爬取 591 → 正規化 → 去重存入 DB → Enrich 詳情 → 篩選 → 摘要通知
                                                                    ↓
                                                          /list 互動式瀏覽
```

1. **爬取** — Playwright 取得 session，requests 呼叫 591 BFF API（買房）或抓取 HTML（租房）
2. **去重** — `entity_fingerprint`（地址+社區 hash）+ 相似度評分，跨仲介識別同一房屋
3. **Enrich** — 買房物件額外取得社區名、車位、公設比、格局等詳情
4. **篩選** — 依設定條件過濾，發送摘要通知引導使用 `/list` 瀏覽
5. **互動** — 分頁列表、區域篩選、展開詳情、標記已讀、收藏

## Environment Variables

| 變數 | 必要 | 預設 | 說明 |
|------|------|------|------|
| `TELEGRAM_BOT_TOKEN` | Yes | - | @BotFather 取得的 Bot Token |
| `TELEGRAM_CHAT_ID` | Yes | - | 授權的 Chat ID |
| `DATABASE_PATH` | No | `data/homedog.db` | SQLite 資料庫路徑 |
| `LOG_LEVEL` | No | `INFO` | 日誌等級 |

## Configuration

所有設定透過 Telegram Bot inline keyboard 管理，儲存在 SQLite `bot_config` 表中。

首次啟動時傳送 `/start` 開始設定引導，之後隨時可用 `/settings` 修改任何參數。

## Listing Deduplication

系統會在寫入前用 `entity_fingerprint + 相似度分數` 做去重，避免同一間房被多位房仲重複入庫。

### Dedup Tuning Knobs

透過 Bot `/settings` 調整去重參數：

- `threshold` (預設 0.82): 越高越保守（降低誤刪，可能漏掉部分重複）
- `price_tolerance` (預設 0.05) / `size_tolerance` (預設 0.08): 允許同屋在不同刊登間的價格/坪數微幅差異

### Historical Cleanup

在 Bot 中使用 `/dedupall` 以 batch 方式執行全庫去重。

## Telegram 縮圖（Google Maps）

可選功能。個人用量通常 <10k 次/月，Google Maps Static Maps + Geocoding 都有每月 10,000 次免費額度。

需求：Google Cloud 專案 + 啟用 Static Maps API 與 Geocoding API + API key。

### Bot 模式設定

將 Maps 設定寫入 SQLite `bot_config`：

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

重啟 bot 後，新通知會附上地圖縮圖，失敗時自動降級為純文字地址。

## Docker

```bash
docker compose up -d      # Start
docker compose logs -f     # View logs
docker compose down        # Stop
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
