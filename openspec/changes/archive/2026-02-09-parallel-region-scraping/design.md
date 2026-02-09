## Context

`scrape_listings()` 以 for loop 逐一爬取每個 region。每個 region 需要：
1. Playwright 啟動 browser → 導航 591 → 取得 session headers (x-csrf-token, deviceid, cookies)
2. 用 requests.Session 分頁呼叫 BFF API

步驟 1 約 5-10 秒，步驟 2 每頁 2-5 秒。兩個 region 合計 30-60 秒。各 region 完全獨立，無共享狀態。

## Goals / Non-Goals

**Goals:**
- 多 region 時並行爬取，縮短整體耗時至接近單一 region 的時間
- 保持 progress callback 正常運作
- 可控制最大並行數

**Non-Goals:**
- 單一 region 內的多頁並行（591 可能 rate limit）
- 租房模式的並行（目前僅支援台北市，只有一個 region）
- Playwright browser instance 共享或 pool

## Decisions

- **使用 `concurrent.futures.ThreadPoolExecutor`**：Playwright 的 sync API 是 blocking I/O，適合 thread-based 並行。不需 asyncio 改造。比 multiprocessing 輕量，無序列化問題。
- **每個 thread 獨立 Playwright browser**：Playwright browser/page 不能跨 thread 使用，每個 worker 各自 bootstrap session。
- **max_workers 預設為 region 數量，上限 4**：避免同時開太多 browser 佔記憶體，也避免 591 rate limit。
- **progress callback 加鎖**：用 `threading.Lock` 保護 callback 呼叫，確保訊息不交錯。
- **錯誤隔離**：單一 region 失敗不影響其他 region，收集並 log 錯誤，回傳成功的結果。

## Risks / Trade-offs

- **記憶體增加** → 多個 Chromium instance 同時運行，每個約 100-200MB。上限 4 workers 限制最大記憶體。
- **591 rate limit** → 各 region 的 API 呼叫可能被視為異常。但 591 以 session/cookie 區分，各 region 獨立 session 應不影響。保留頁間 delay。
- **Playwright thread safety** → 官方文件明確支持每個 thread 各自建立 browser instance。
