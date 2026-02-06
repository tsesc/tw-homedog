## Why

台灣主要房地產平台（591）資訊更新頻繁但缺乏主動通知機制，使用者需反覆手動查詢，容易錯過高品質或短時間上架的物件。現有 `anarolabs/591-taiwan-apartment-scraper` 已具備爬蟲與評分能力，但缺少持久化存儲、去重機制、條件比對引擎與即時通知功能。本變更將其改造為可長期自動運行的房地產監控通知系統。

## What Changes

- 新增 SQLite 本地資料庫，存儲所有爬取的物件與通知紀錄
- 新增資料正規化模組，將 591 原始資料轉為統一結構
- 新增條件比對引擎，支援價格、坪數、行政區、關鍵字篩選
- 新增 Telegram Bot 通知模組，符合條件的新物件即時推送
- 新增 YAML 設定檔支援搜尋條件參數化
- 新增排程機制（cron），定期自動執行爬取流程
- 重構現有爬蟲模組，整合 Playwright headless 模式與反爬策略
- 建立完整的 Python 專案結構（uv 管理、pyproject.toml）

## Capabilities

### New Capabilities

- `scraper-591`: 基於 Playwright 的 591 爬蟲模組，支援搜尋條件參數化、失敗重試、timeout 控制、反爬策略
- `data-storage`: SQLite 本地存儲，包含 listings 與 notifications_sent 表，支援去重（source + listing_id / content_hash）
- `data-normalizer`: 將 591 原始爬取資料轉為統一 listing 結構
- `match-engine`: 條件比對引擎，支援價格範圍、坪數、行政區、關鍵字 include/exclude、上架時間篩選
- `telegram-notifier`: Telegram Bot API 通知模組，格式化房源訊息推送，同一物件只通知一次
- `scheduler`: 排程執行控制，支援 cron 定期觸發，可配置執行間隔
- `config-manager`: YAML 設定檔管理，統一管理搜尋條件、通知設定、爬蟲參數

### Modified Capabilities

（無既有 specs，此為全新專案）

## Impact

- **程式碼**: 基於 base repo 重構，新建完整 Python package 結構
- **依賴**: Playwright, SQLite3（內建）, python-telegram-bot, PyYAML, BeautifulSoup4, requests
- **系統**: 需要 Telegram Bot Token（透過 BotFather 建立）
- **部署**: 支援本地 / VPS / NAS，透過 cron 或 systemd timer 排程
- **資料**: 本地 SQLite 檔案，無外部資料庫依賴
