## 1. Core Implementation

- [x] 1.1 Refactor `scrape_listings()` to use `ThreadPoolExecutor` for multi-region parallel scraping; single region 直接呼叫不走 thread pool
- [x] 1.2 Extract per-region scrape logic into `_scrape_single_region()` helper，接收 region_id 和 config，回傳 list[dict]
- [x] 1.3 Add thread-safe progress callback wrapper using `threading.Lock`
- [x] 1.4 Add error isolation: catch per-region exceptions, log error, continue collecting other regions' results

## 2. Configuration

- [x] 2.1 Add `scraper.max_workers` config field（預設 4），在 Config dataclass 和 db_config DEFAULTS 中加入

## 3. Tests

- [x] 3.1 Unit test: multiple regions returns combined results (mock scrape_buy_listings)
- [x] 3.2 Unit test: single region skips thread pool, direct call
- [x] 3.3 Unit test: one region failure returns other regions' results
- [x] 3.4 Unit test: progress callback invoked from parallel threads without error
