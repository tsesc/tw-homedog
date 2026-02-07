## Why

目前 tw-homedog 使用靜態 YAML 配置檔搭配 CLI 執行，每次修改參數都需要手動編輯 config.yaml 後重啟。部署到 Linux 伺服器後，使用者無法方便地調整搜尋條件。需要將配置管理遷移至 DB 並透過 Telegram Bot inline 互動介面進行全面的參數設定，同時容器化部署並使用 Python 排程替代 cron，強化 logging 方便 production 環境 debug。

## What Changes

- **Telegram Bot 互動介面**：使用 `python-telegram-bot` 的 ConversationHandler + InlineKeyboardMarkup 實作完整的設定互動流程，支援 `/start` 初始設定引導、`/settings` 即時修改任意參數、`/status` 查看當前設定與執行狀態
- **DB Config 儲存**：新增 `bot_config` 表取代 YAML 配置，透過 SQLite 儲存所有搜尋/通知參數，支援即時更新無需重啟
- **Docker 化部署**：使用 `ghcr.io/astral-sh/uv` 官方映像建構，Playwright chromium 打包在容器內，一鍵 `docker compose up` 啟動
- **Python 定時任務**：使用 `APScheduler` 取代 cron，在應用內管理排程，支援透過 Bot 動態調整執行頻率
- **Logging 強化**：結構化 logging 搭配 RotatingFileHandler，production 預設 INFO，可透過環境變數或 Bot 指令調整等級
- **架構重構**：入口點從 CLI argparse 改為 long-running Bot process，pipeline 作為排程任務自動執行

## Capabilities

### New Capabilities
- `telegram-bot-handler`: Telegram Bot 長駐程序，處理使用者指令、inline keyboard 互動、ConversationHandler 設定流程
- `db-config`: SQLite-based 配置儲存與管理，取代 YAML 靜態檔案，支援即時讀寫與驗證
- `scheduler`: APScheduler 整合，管理 pipeline 定時執行，支援動態調整排程頻率
- `docker-deployment`: Dockerfile + docker-compose.yml，包含 Playwright chromium、volume 持久化、環境變數配置
- `structured-logging`: 強化的 logging 系統，RotatingFileHandler、可配置等級、結構化輸出格式

### Modified Capabilities
<!-- 無既有 spec 需要修改 -->

## Impact

- **新增依賴**：`apscheduler>=3.10`
- **入口點變更**：`__main__.py` 從 CLI 模式改為 Bot long-running process，保留 `--cli` fallback
- **Config 遷移**：首次啟動時可從現有 `config.yaml` 匯入到 DB，之後完全由 Bot 互動管理
- **Storage schema**：新增 `bot_config` 表、`scheduler_state` 表
- **檔案新增**：`bot.py`（Bot handler）、`db_config.py`（DB config 管理）、`scheduler.py`（排程管理）、`Dockerfile`、`docker-compose.yml`
- **向後相容**：保留 CLI 模式（`--cli` flag），現有 YAML config 可透過 migration 指令匯入 DB
