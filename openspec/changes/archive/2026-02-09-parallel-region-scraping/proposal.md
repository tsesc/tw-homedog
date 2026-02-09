## Why

多地區搜尋（如台北市+新北市）時，`scrape_listings()` 以 for loop 逐一爬取每個 region，每個 region 需要獨立的 Playwright session bootstrap + 多頁 API 呼叫。兩個 region 加起來要 30-60 秒。各 region 之間無資料相依，可以並行執行來縮短整體耗時。

## What Changes

- `scrape_listings()` 改用 `concurrent.futures.ThreadPoolExecutor` 並行爬取各 region
- 每個 region 在獨立 thread 中建立自己的 Playwright session 和 requests.Session
- progress callback 改為 thread-safe（已有基礎，需確認）
- 可設定 `max_workers` 控制並行數（預設 = region 數量，上限 4）

## Capabilities

### New Capabilities
- `parallel-scraping`: 多地區並行爬取能力，將 `scrape_listings()` 的 sequential region loop 改為 ThreadPoolExecutor 並行

### Modified Capabilities

## Impact

- `src/tw_homedog/scraper.py` — `scrape_listings()` 函式重構
- Playwright browser instance 需在每個 thread 獨立建立（Playwright 不支援跨 thread 共享）
- 記憶體使用會略增（多個 browser instance 同時存在）
- 對 591 的請求會變成並行，需注意不要觸發 rate limit
