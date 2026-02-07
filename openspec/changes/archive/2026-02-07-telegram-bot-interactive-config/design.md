## Context

tw-homedog 目前是一個 CLI 工具，透過 YAML 配置 + argparse 子指令執行 scrape/match/notify pipeline。部署到 Linux 伺服器後，使用者無法方便地修改搜尋參數。現有的 Telegram 整合僅用於單向推送通知，尚未利用 Bot API 的互動能力。

現有架構：`config.yaml` → `load_config()` → `Config dataclass` → pipeline modules
目標架構：`SQLite bot_config` → `DbConfig` → pipeline modules，同時 Telegram Bot 作為 long-running 入口點管理設定與排程。

## Goals / Non-Goals

**Goals:**
- 透過 Telegram Bot inline keyboard 完成所有配置管理（region、districts、price、size、keywords、mode、排程頻率）
- 配置持久化至 SQLite，支援即時更新無需重啟
- Docker 化部署，`docker compose up` 一鍵啟動
- 內建 Python 排程器取代 cron
- 結構化 logging，production 預設 INFO，可動態調整

**Non-Goals:**
- 多使用者/多 chat 支援（單一 Bot 對應單一 chat_id）
- Web UI 或其他通知管道
- 資料庫從 SQLite 遷移至 PostgreSQL
- 591 scraper 邏輯本身的改動

## Decisions

### 1. Bot 框架：python-telegram-bot Application（已有依賴）
**選擇**：繼續使用 `python-telegram-bot` 的 `Application` + `ConversationHandler`
**替代方案**：aiogram、telethon
**理由**：專案已依賴 `python-telegram-bot>=22.6`，其 `Application` 類別支援 long-polling + job queue，ConversationHandler 原生支援多步驟互動流程，不需引入新依賴。

### 2. 配置儲存：SQLite JSON column
**選擇**：`bot_config` 表使用 `key TEXT PRIMARY KEY, value TEXT` 結構，value 存 JSON 序列化值
**替代方案**：單一 JSON blob row、每欄位獨立 column
**理由**：key-value 結構靈活支援新增欄位，無需 schema migration。JSON value 支援複合型別（如 districts list）。比單一 blob 更容易原子性更新個別設定。

### 3. 排程器：python-telegram-bot 內建 JobQueue
**選擇**：使用 `Application.job_queue`（基於 APScheduler）
**替代方案**：獨立 APScheduler、schedule 套件、asyncio.sleep loop
**理由**：`python-telegram-bot` 的 `Application` 已內建 `JobQueue`（底層是 APScheduler），可以直接 `job_queue.run_repeating()` 排程 pipeline，不需額外依賴。支援動態調整頻率、暫停/恢復。

### 4. 入口點架構
**選擇**：`__main__.py` 根據是否有 `--cli` flag 分流到 CLI mode 或 Bot mode
**理由**：保持向後相容。Bot mode 啟動 `Application.run_polling()`，CLI mode 保留現有 argparse 行為。

### 5. Docker 策略
**選擇**：Multi-stage build，base 用 `ghcr.io/astral-sh/uv:0.5-python3.12-bookworm-slim`，runtime 安裝 Playwright chromium
**理由**：遵循專案 Python Docker 標準。Playwright chromium 必須在 runtime image 中因為 scraper 需要。使用 `playwright install --with-deps chromium` 安裝。

### 6. Logging 策略
**選擇**：`logging.config.dictConfig` + `RotatingFileHandler` + `StreamHandler`
**替代方案**：structlog、loguru
**理由**：使用 stdlib logging 避免新依賴。RotatingFileHandler 防止 log 檔案無限增長。`LOG_LEVEL` 環境變數控制等級。Bot 指令 `/loglevel` 可動態調整。

## Risks / Trade-offs

- **Long-polling 穩定性** → `Application.run_polling()` 內建重試機制，加上 Docker restart policy `unless-stopped` 保護
- **Playwright 容器體積大** → chromium + deps 約 400MB，但 scraper 功能必須，無法避免。使用 multi-stage build 減少不必要的 build tools
- **SQLite 單寫者限制** → 不影響，因為只有單一 Bot process 寫入。WAL mode 已啟用
- **Config 遷移風險** → 提供 `migrate-config` 指令從 YAML 匯入 DB，保留原 YAML 作 backup
- **去除 APScheduler 獨立依賴** → 使用 `python-telegram-bot` 內建 JobQueue 避免版本衝突，但被綁定在 Bot mode 中。CLI mode 不具備排程功能（設計如此）
