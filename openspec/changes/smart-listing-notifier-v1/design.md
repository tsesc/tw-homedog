## Context

現有 `anarolabs/591-taiwan-apartment-scraper` 是一個 Python 專案，使用 Playwright 爬取 591 租屋資料，具備三階段流程：收集 listing ID → 提取詳情 → 評分輸出。但它是一次性批次工具，缺少持久化存儲、去重、條件比對與通知能力。

本設計將其改造為可長期自動運行的監控通知系統，核心是加入 SQLite 存儲層、條件比對引擎與 Telegram 推播，並透過 cron 排程定期執行。

專案使用 Python + uv 管理，遵循既有 CLAUDE.md 中的 Python 專案標準。

## Goals / Non-Goals

**Goals:**
- 建立模組化的 Python package 結構，便於長期維護與擴充
- 591 爬蟲支援搜尋條件參數化與反爬策略
- SQLite 本地存儲與去重，避免重複處理
- 條件比對引擎支援多維度篩選（價格、坪數、區域、關鍵字）
- Telegram Bot 即時通知新符合條件物件
- YAML 設定檔統一管理所有參數
- cron 排程自動化，可連續運行 30 天無人工干預

**Non-Goals:**
- 不提供 Web UI（未來擴充）
- 不支援多用戶（第一版為個人使用）
- 不做 AI 評分或圖片分析
- 不支援 591 以外的平台（第一版）
- 不破解登入或付費牆

## Decisions

### D1: 專案結構 — 全新 package 而非 fork 修改

**決定**: 建立全新 `tw_homedog` Python package，從 base repo 提取有用的爬蟲邏輯，而非直接 fork 修改。

**理由**: Base repo 的結構（flat scripts, requirements.txt, setup.py）不適合長期維護。新 package 使用 uv + pyproject.toml，模組化設計便於未來加入新站點。

**替代方案**: 直接 fork 修改 → 受限於原始結構，難以擴充。

### D2: 資料庫 — SQLite with raw SQL

**決定**: 使用 SQLite3（Python 內建），直接寫 raw SQL，不使用 ORM。

**理由**:
- SQLite 零配置、零外部依賴，適合個人單機使用
- 資料模型簡單（2 張表），ORM 是過度工程
- 便於 debug 和直接查詢

**替代方案**:
- SQLAlchemy ORM → 對此規模過重
- PostgreSQL → 需要額外部署

### D3: 爬蟲策略 — Playwright headless + requests 混合

**決定**: 使用 Playwright headless 瀏覽搜尋結果頁收集 listing ID，使用 requests + BeautifulSoup 抓取個別物件詳情。

**理由**: 搜尋結果頁有 JS 渲染需要瀏覽器，個別物件頁可用 HTTP 直接取得，混合方式平衡效率與可靠性。沿用 base repo 的成熟做法。

**替代方案**: 全部用 Playwright → 慢且耗資源。全部用 requests → 搜尋頁無法正確渲染。

### D4: 通知 — python-telegram-bot 套件

**決定**: 使用 `python-telegram-bot` 套件透過 Telegram Bot API 推送通知。

**理由**: 成熟穩定、API 完整、社群活躍。Telegram 適合即時通知場景，支援 Markdown 格式化訊息。

**替代方案**:
- 直接 HTTP 呼叫 Bot API → 需自行處理 retry/error
- Line Notify → API 較受限

### D5: 設定檔 — YAML 格式

**決定**: 使用 YAML 設定檔（`config.yaml`），搭配 `config.example.yaml` 範例。

**理由**: YAML 可讀性高，支援巢狀結構與註解，適合人工編輯。PRD 也建議 YAML/JSON，YAML 比 JSON 更友善。

### D6: 排程 — 系統 cron

**決定**: 使用系統 cron 觸發 Python 腳本，不內建排程器。

**理由**: Unix 哲學——讓專門工具做排程。cron 穩定可靠，使用者可自由設定頻率。避免在 Python 中維護長駐進程。

**替代方案**: APScheduler → 需要常駐進程，增加複雜度。

### D7: 主程式入口 — CLI with subcommands

**決定**: 提供 `python -m tw_homedog` CLI 入口，支援子命令：`scrape`, `notify`, `run`（完整流程）。

**理由**: 便於 cron 呼叫、手動調試、未來擴充。`run` 命令組合完整流程供排程使用。

## Risks / Trade-offs

| 風險 | 緩解策略 |
|------|---------|
| 591 改版導致爬蟲失敗 | 模組化 selector/parser，集中管理提取邏輯，加入健康檢查 log |
| IP 被封鎖 | 隨機 delay（2-5s）、User-Agent rotation、降低頻率（每 15 分鐘一次） |
| Telegram API rate limit | 批次通知間加入延遲、單次最多推送 10 則 |
| SQLite 並發寫入衝突 | 單進程執行，使用 WAL mode |
| 設定檔格式錯誤 | 啟動時 schema validation，清楚的錯誤訊息 |

## Migration Plan

此為全新專案，無需遷移。部署步驟：

1. Clone repo，`uv sync` 安裝依賴
2. 複製 `config.example.yaml` → `config.yaml`，填入搜尋條件與 Telegram Bot Token
3. `uv run python -m tw_homedog run` 測試完整流程
4. 設定 cron job：`*/15 * * * * cd /path/to/tw-homedog && uv run python -m tw_homedog run`

## Open Questions

- 591 是否有更穩定的 API 端點可替代 HTML 爬取？（需持續觀察）
- 是否需要 proxy 支援？（第一版先不加，視實際被封情況決定）
