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

## 專案概述

台灣 591 房屋網的智慧通知系統。自動爬取買房/租房物件，依使用者設定的條件篩選後，透過 Telegram Bot 推送通知。

## 運作流程

### Pipeline: `scraper → normalizer → storage → matcher → notifier`

1. **爬取 (scraper.py)** — 從 591 網站抓取房屋物件原始資料
   - 買房模式：Playwright 取得 session → requests 呼叫 BFF API (`bff-house.591.com.tw`)
   - 租房模式：Playwright 收集物件 ID → requests 抓取詳情 HTML（僅台北市驗證過）
   - 支援多地區同時搜尋：對每個 region 分別建立 session 並爬取
2. **正規化 (normalizer.py)** — 將原始資料轉換為統一格式，產生 SHA256 content hash 用於去重
3. **儲存 (storage.py)** — 寫入 SQLite，以 `(source, listing_id)` 和 `raw_hash` 雙重去重
4. **篩選 (matcher.py)** — 從 DB 取出所有「未讀」物件，依條件過濾：
   - 價格範圍（買房單位：萬，租房單位：元）
   - 區域（district 名稱比對）
   - 最小坪數
   - 關鍵字包含/排除（搜尋 title、kind_name、room、address、tags、parking_desc、shape_name、community_name）
5. **通知** — Pipeline 完成後發送摘要訊息（「有 N 筆未讀物件符合條件，使用 /list 查看」），使用者透過 `/list` 互動式瀏覽、篩選、查看詳情並標記已讀

### 買房模式的 Enrichment

符合篩選條件的買房物件會額外呼叫 detail API 取得：parking_desc、public_ratio、manage_price_desc、fitment、shape_name、community_name、main_area、direction。Enrichment 結果存回 DB 的 `is_enriched` 欄位，避免重複呼叫。Enrich 後會重新執行 matcher（因為新欄位可能影響關鍵字篩選結果）。

## DB 結構 (SQLite)

五張表：

- **listings** — 所有爬取到的物件（不論是否符合條件都存）。以 `(source, listing_id)` 唯一識別，`raw_hash` 用於內容去重，`entity_fingerprint` 用於跨仲介去重。包含基本欄位（title, price, district, size_ping, floor, url）、enrichment 欄位（community_name, parking_desc, public_ratio 等）和 `is_enriched` 標記。
- **notifications_sent** — 已發送通知的紀錄。以 `(source, listing_id, channel)` 唯一識別。（歷史遺留，新版改用 listings_read）
- **listings_read** — 使用者已讀物件追蹤。以 `(source, listing_id)` 唯一識別，記錄讀取時的 `raw_hash`。當物件 raw_hash 變更（內容更新）時自動重新視為未讀。
- **favorites** — 使用者收藏的物件。以 `(source, listing_id)` 唯一識別，透過 `/list` 詳情頁的星號按鈕操作。
- **bot_config** — Bot 模式的設定存儲（key-value JSON）。所有設定透過 Telegram inline keyboard 管理。

## Architecture

兩種運作模式：
- **Bot mode** (預設)：長駐 Telegram Bot，透過 inline keyboard 設定，JobQueue 排程自動執行
- **CLI mode** (`cli` 子指令)：一次性執行 pipeline，使用 YAML 設定檔

### 主要模組

- **bot.py** — Telegram Bot Application，ConversationHandler 處理 setup flow，InlineKeyboard 處理 settings，JobQueue 排程
- **db_config.py** — SQLite key-value 設定存儲，`build_config()` 從 DB 組建 Config dataclass。支援 `search.region`（舊格式）和 `search.regions`（新格式 list）的向後相容
- **regions.py** — 全台 22 縣市的 region code 和 district section code。買賣/租房的 section code 完全不同（如內湖區：buy=10, rent=5）。Section codes 須與 591 BFF API 實際回傳值一致
- **scraper.py** — 591 爬蟲。`scrape_listings()` 為統一入口，依 mode 分派到 `scrape_buy_listings()` 或 `scrape_rent_listings()`
- **config.py** — YAML 設定載入與驗證（CLI mode）。`SearchConfig.regions: list[int]` 支援多地區
- **dedup.py** — 物件去重引擎。使用 `entity_fingerprint`（地址+社區正規化後的 hash）識別同一實體，`score_duplicate()` 計算兩物件相似度（標題、地址、價格、坪數加權），超過門檻視為重複
- **dedup_cleanup.py** — 歷史去重清理。掃描 DB 中 fingerprint 相同的群組，規劃合併（保留 canonical listing，遷移關聯表記錄），支援 dry-run 和 batch apply
- **map_preview.py** — Google Maps Static API 地圖縮圖產生與快取。支援 Geocoding API 地址→座標轉換，檔案級快取（可設 TTL），失敗時自動降級
- **templates.py** — 預設設定模板，用於 Bot 快速設定

## Bot Commands

- `/start` — 首次設定引導或歡迎訊息
- `/list` — 互動式瀏覽未讀物件（分頁、區域篩選、詳情展開、標記已讀）
- `/favorites` — 查看最愛物件
- `/settings` — 透過 inline keyboard 修改任何參數（模式、地區、區域、價格、坪數、關鍵字、頁數、排程）
- `/status` — 當前設定摘要、排程狀態、DB 統計（含未讀數）
- `/help` — 指令列表
- `/run` — 手動觸發 pipeline（完成後顯示未讀物件摘要，引導使用 /list 查看）
- `/dedupall [batch_size]` — 以 batch 方式執行全庫去重，直到無剩餘群組
- `/pause` / `/resume` — 控制自動排程
- `/loglevel DEBUG|INFO|WARNING|ERROR` — 動態調整 log level
- `/config_export` — 匯出目前設定為 JSON
- `/config_import` — 匯入設定（JSON）

## Key Technical Gotchas

- 591 BFF API `total` 欄位是 **string**，必須轉 `int`
- 591 API `totalPrice` 參數**被忽略** — 價格過濾必須在 matcher 端做
- Playwright `document.cookie` 在 591 被擋 — 必須用 `page.context.cookies()`
- 買房價格單位是萬，租房是元 — config `price.min/max` 必須對應模式
- **BUY_SECTION_CODES 必須與 591 BFF API 實際值一致**。可用 API `regionid=X&section=Y` 驗證 `section_name` 回傳值。各地區 code 不是連續或可預測的
- `notifier.py` 在 sync code 中使用 `asyncio.run()` 呼叫 Telegram async API
- `python-telegram-bot[job-queue]` extra 是 JobQueue/APScheduler 所需

## Environment Variables (Bot mode)

- `TELEGRAM_BOT_TOKEN` (required) — Bot token from @BotFather
- `TELEGRAM_CHAT_ID` (required) — Authorized chat ID
- `DATABASE_PATH` (default: `data/homedog.db`) — SQLite DB path
- `LOG_LEVEL` (default: `INFO`) — Logging level

## Config

**Bot mode**: Config 存在 SQLite `bot_config` 表，透過 Telegram inline keyboard 管理。
**CLI mode**: YAML config at `config.yaml` (copy from `config.example.yaml`)。

Config 支援中文優先格式：`regions: ["台北市", "新北市"]`、`districts: ["內湖區", "南港區"]`。英文名（`region: 1`、`districts: ["Neihu"]`）仍可使用。全台 22 縣市支援買房模式；租房僅台北市。

## Testing

Tests use `tmp_path` for isolated SQLite DBs. External APIs (Telegram, 591) are mocked. Test helpers like `_listing(**overrides)` create test data with sensible defaults. 目前共 203 個測試。
