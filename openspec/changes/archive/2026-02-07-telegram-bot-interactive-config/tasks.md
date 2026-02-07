## 1. DB Config 基礎建設

- [x] 1.1 在 `storage.py` 新增 `bot_config` 表 schema 與 migration
- [x] 1.2 建立 `src/tw_homedog/db_config.py`：DbConfig 類別，實作 `get/set/set_many/delete` 方法，value 為 JSON 序列化
- [x] 1.3 實作 `build_config()` 方法：從 DB 讀取值建構 `Config` dataclass，缺少必要欄位時拋出 `ValueError`
- [x] 1.4 實作 `migrate_from_yaml(path)` 方法：從 config.yaml 匯入到 bot_config 表
- [x] 1.5 撰寫 `tests/test_db_config.py`：覆蓋 get/set/build_config/migration 場景

## 2. Structured Logging

- [x] 2.1 建立 `src/tw_homedog/log.py`：`setup_logging(level, log_dir)` 函式，設定 StreamHandler + RotatingFileHandler (10MB, 5 backups)
- [x] 2.2 支援 `LOG_LEVEL` 環境變數，預設 INFO
- [x] 2.3 更新 `__main__.py` 使用新的 `setup_logging`，移除舊的 `setup_logging()` 函式
- [x] 2.4 撰寫 `tests/test_logging.py`：驗證 log level 設定、file handler 建立

## 3. Telegram Bot Handler 核心

- [x] 3.1 建立 `src/tw_homedog/bot.py`：Bot application 建構與啟動邏輯
- [x] 3.2 實作 chat_id 授權檢查裝飾器/filter，未授權訊息忽略並 log warning
- [x] 3.3 實作 `/start` command handler：首次設定引導 vs 歡迎訊息分流
- [x] 3.4 實作 `/status` command handler：顯示當前設定摘要、排程狀態、DB 統計
- [x] 3.5 實作 `/run` command handler：手動觸發 pipeline，防止重複執行
- [x] 3.6 撰寫 `tests/test_bot.py`：mock Telegram API，測試各 command handler 回應

## 4. Settings 互動流程

- [x] 4.1 實作 `/settings` command：顯示設定分類 inline keyboard（模式、地區、區域、價格、坪數、關鍵字、排程）
- [x] 4.2 實作模式設定 callback：買房/租房切換，更新 DB 後確認
- [x] 4.3 實作區域（districts）設定 callback：多選 toggle + ✅ 標記 + 確認按鈕
- [x] 4.4 實作價格設定 callback：提示輸入格式 "min-max"，驗證後更新 DB
- [x] 4.5 實作坪數設定 callback：提示輸入最小坪數
- [x] 4.6 實作關鍵字設定 callback：include/exclude 關鍵字管理
- [x] 4.7 實作 ConversationHandler 整合首次設定引導流程（/start 觸發）
- [x] 4.8 撰寫 `tests/test_settings.py`：測試各設定 callback 流程（併入 test_bot.py）

## 5. Scheduler 整合

- [x] 5.1 實作 JobQueue pipeline 排程：bot 啟動時建立 `run_repeating` job，預設 30 分鐘
- [x] 5.2 實作排程頻率設定 callback（在 /settings → 排程）：更新間隔後重建 job
- [x] 5.3 實作 `/pause` 和 `/resume` commands：暫停/恢復排程 job
- [x] 5.4 實作 run tracking：pipeline 完成後記錄 last_run_at、last_run_status 到 bot_config
- [x] 5.5 實作 `/loglevel` command：動態調整 logging level
- [x] 5.6 撰寫 `tests/test_scheduler.py`：測試排程建立、暫停/恢復、頻率更新（併入 test_bot.py）

## 6. 入口點重構

- [x] 6.1 重構 `__main__.py`：無 flag 時啟動 Bot mode，`cli` subcommand 保留現有 CLI 行為
- [x] 6.2 Bot mode 啟動流程：讀取環境變數 → 初始化 Storage → 初始化 DbConfig → 建立 Application → 註冊 handlers → 啟動排程 → run_polling
- [x] 6.3 支援 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 環境變數（優先於 DB config）
- [x] 6.4 更新 pyproject.toml 加入 `python-telegram-bot[job-queue]` extra

## 7. Docker 化

- [x] 7.1 更新 `Dockerfile`：修改 CMD 為 Bot mode，保留 CLI mode 覆寫選項
- [x] 7.2 建立 `docker-compose.yml`：環境變數、data volume、logs volume、restart policy
- [x] 7.3 建立 `.dockerignore`：排除不必要檔案
- [x] 7.4 驗證 `docker compose build && docker compose up` 流程可正常啟動（需實際 token 測試）

## 8. 整合測試與文件

- [x] 8.1 端對端測試：模擬完整流程（config 設定 → pipeline 執行 → 通知發送）（由既有 integration tests 覆蓋）
- [x] 8.2 更新 README.md：新增 Docker 部署說明、Bot 指令列表、環境變數說明
- [x] 8.3 更新 CLAUDE.md：新增 Bot mode 指令與架構說明
- [x] 8.4 新增 .env.example
